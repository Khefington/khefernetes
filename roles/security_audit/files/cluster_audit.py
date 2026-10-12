#!/usr/bin/env python3
"""READ-ONLY security audit of the Kubernetes cluster and of Jellyfin's own settings. Changes nothing.

Run on a control plane node:  python3 cluster_audit.py --kubectl "/var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml" [--media-namespace media]

Secret VALUES are never read: Secrets are listed by name/type only, and the Jellyfin API key is used in memory to ask
Jellyfin for its settings. Output format is the same as host_audit.py: [OK] / [INFO] / [WARN] topic: message.
"""
import argparse
import base64
import json
import shlex
import subprocess
import sys
import urllib.error
import urllib.request

COUNTS = {"OK": 0, "INFO": 0, "WARN": 0}
SYSTEM_NS = {"kube-system", "kube-public", "kube-node-lease"}


def emit(level, topic, msg):
    COUNTS[level] += 1
    print("[%s] %s: %s" % (level, topic, msg))


class Kube:
    def __init__(self, kubectl):
        self.base = shlex.split(kubectl)

    def raw(self, *args):
        try:
            p = subprocess.run(self.base + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        return p.stdout if p.returncode == 0 else None

    def items(self, *args):
        out = self.raw("get", *args, "-o", "json")
        if out is None:
            return None
        try:
            return json.loads(out).get("items", [])
        except ValueError:
            return None


def is_system(ns):
    return ns in SYSTEM_NS


# --------------------------------------------------------------------------------------------------
def check_nodes(k):
    nodes = k.items("nodes")
    if nodes is None:
        emit("WARN", "cluster", "kubectl could not list nodes: the audit cannot continue")
        return False
    for n in nodes:
        info = n["status"]["nodeInfo"]
        emit("INFO", "nodes", "%s: Kubernetes %s, %s, kernel %s" % (n["metadata"]["name"], info.get("kubeletVersion"), info.get("osImage"), info.get("kernelVersion")))
    return True


def check_namespaces(k):
    nss = k.items("namespaces") or []
    policies = k.items("networkpolicies", "-A") or []
    per_ns = {}
    for p in policies:
        per_ns[p["metadata"]["namespace"]] = per_ns.get(p["metadata"]["namespace"], 0) + 1
    for ns in nss:
        name = ns["metadata"]["name"]
        labels = ns["metadata"].get("labels") or {}
        enforce = labels.get("pod-security.kubernetes.io/enforce")
        if is_system(name) or name == "default":
            emit("INFO", "namespace", "%s (system): pod-security enforce=%s, %d network policies" % (name, enforce or "none", per_ns.get(name, 0)))
            continue
        if enforce in ("restricted", "baseline"):
            emit("OK", "namespace", "%s: pod-security enforce=%s" % (name, enforce))
        elif enforce == "privileged":
            emit("INFO", "namespace", "%s: pod-security level is explicitly 'privileged' (fine for components that need host access, e.g. a load balancer)" % name)
        else:
            emit("WARN", "namespace", "%s: no pod-security enforcement (a pod asking for privileged access would be admitted)" % name)
        n = per_ns.get(name, 0)
        if n:
            emit("OK", "namespace", "%s: %d network policies" % (name, n))
        else:
            emit("WARN", "namespace", "%s: no network policies, so every pod in the cluster can reach every pod here (Canal can enforce them)" % name)


# Components that legitimately need more than an ordinary app: (namespace, pod name prefix) -> why.
ACCEPTED = {
    ("metallb-system", "speaker"): "announces the ingress address on the LAN, so it needs host networking and raw sockets",
    ("metallb-system", "controller"): "MetalLB's controller (upstream manifest; no limits or seccomp profile set)",
    ("intel-gpu-plugin", "intel-gpu-plugin"): "the GPU device plugin must see /dev/dri, /sys/class/drm and the kubelet device-plugin socket",
    ("local-path-storage", "local-path-provisioner"): "creates the node-local volumes (Jellyfin's database lives on one)",
}


def accepted_reason(ns, name):
    for (ans, prefix), why in ACCEPTED.items():
        if ns == ans and name.startswith(prefix):
            return why
    return None


def containers_of(pod):
    spec = pod["spec"]
    return (spec.get("initContainers") or []) + (spec.get("containers") or [])


def check_pods(k):
    pods = k.items("pods", "-A") or []
    sys_findings = {}
    images = {}
    for pod in pods:
        ns, name = pod["metadata"]["namespace"], pod["metadata"]["name"]
        spec = pod["spec"]
        psc = spec.get("securityContext") or {}
        findings = []
        for key in ("hostNetwork", "hostPID", "hostIPC"):
            if spec.get(key):
                findings.append(key)
        for v in spec.get("volumes") or []:
            if "hostPath" in v:
                findings.append("hostPath %s" % v["hostPath"].get("path"))
        for c in containers_of(pod):
            sc = c.get("securityContext") or {}
            cname = c["name"]
            img = c["image"]
            images.setdefault(img, []).append("%s/%s" % (ns, name))
            if sc.get("privileged"):
                findings.append("%s: PRIVILEGED" % cname)
            if sc.get("allowPrivilegeEscalation") is not False:
                findings.append("%s: can gain privileges" % cname)
            uid = sc.get("runAsUser", psc.get("runAsUser"))
            nonroot = sc.get("runAsNonRoot", psc.get("runAsNonRoot"))
            if uid == 0 or (nonroot is not True and not uid):
                findings.append("%s: runs as root" % cname)
            if "ALL" not in [x.upper() for x in ((sc.get("capabilities") or {}).get("drop") or [])]:
                findings.append("%s: keeps default capabilities" % cname)
            if not (c.get("resources") or {}).get("limits", {}).get("memory"):
                findings.append("%s: no memory limit" % cname)
            seccomp = (sc.get("seccompProfile") or psc.get("seccompProfile") or {}).get("type")
            if not seccomp:
                findings.append("%s: no seccomp profile" % cname)
        if is_system(ns):
            sys_findings[ns] = sys_findings.get(ns, 0) + len(findings)
        elif findings and accepted_reason(ns, name):
            emit("INFO", "pod", "%s/%s accepted (%s): %s" % (ns, name, accepted_reason(ns, name), "; ".join(findings)))
        elif findings:
            emit("WARN", "pod", "%s/%s: %s" % (ns, name, "; ".join(findings)))
        else:
            emit("OK", "pod", "%s/%s: no privileged access, no host access, non-root, capabilities dropped, seccomp on" % (ns, name))
    for ns, n in sorted(sys_findings.items()):
        emit("INFO", "pod", "%s: %d settings flagged on system pods (expected: Kubernetes itself needs host access; the CIS profile covers these)" % (ns, n))
    for img, users in sorted(images.items()):
        tag = img.rsplit(":", 1)[1] if ":" in img.rsplit("/", 1)[-1] else ""
        if "@sha256:" in img:
            continue
        if tag in ("", "latest"):
            emit("WARN", "images", "%s uses a floating tag (%s)" % (img, ", ".join(users[:2])))
    emit("INFO", "images", "%d distinct images; pinned by tag, not digest (digests would stop a tag being swapped under you)" % len(images))


def check_exposure(k):
    for s in k.items("services", "-A") or []:
        t = s["spec"].get("type")
        ns, name = s["metadata"]["namespace"], s["metadata"]["name"]
        if t == "NodePort":
            ports = ",".join(str(p.get("nodePort")) for p in s["spec"]["ports"])
            emit("WARN", "services", "%s/%s is a NodePort (%s): open on every node" % (ns, name, ports))
        elif t == "LoadBalancer":
            ing = ",".join(i.get("ip", "?") for i in (s["status"].get("loadBalancer") or {}).get("ingress") or [])
            ports = ",".join(str(p["port"]) for p in s["spec"]["ports"])
            emit("INFO", "services", "%s/%s is a LoadBalancer on %s (ports %s)" % (ns, name, ing or "pending", ports))
    for i in k.items("ingresses", "-A") or []:
        ns, name = i["metadata"]["namespace"], i["metadata"]["name"]
        hosts = [r.get("host", "*") for r in i["spec"].get("rules") or []]
        if "*" in hosts:
            emit("INFO", "ingress", "%s/%s also answers requests with ANY host name (for example http://<ingress IP>): remove that rule once DNS works everywhere" % (ns, name))
            hosts = [h for h in hosts if h != "*"]
        if i["spec"].get("tls"):
            emit("OK", "ingress", "%s/%s (%s) serves HTTPS" % (ns, name, ", ".join(hosts)))
        else:
            emit("WARN", "ingress", "%s/%s (%s) is plain HTTP: logins and video cross the network in clear text" % (ns, name, ", ".join(hosts)))


def check_rbac(k):
    for b in k.items("clusterrolebindings") or []:
        if b["roleRef"]["name"] != "cluster-admin":
            continue
        subs = b.get("subjects") or []
        custom = [s for s in subs if not s.get("name", "").startswith(("system:", "helm-"))]
        if custom:
            emit("WARN", "rbac", "ClusterRoleBinding %s gives cluster-admin to %s" % (b["metadata"]["name"], ", ".join("%s %s" % (s["kind"], s["name"]) for s in custom)))
        else:
            emit("INFO", "rbac", "ClusterRoleBinding %s gives cluster-admin to %s (built-in)" % (b["metadata"]["name"], ", ".join(s["name"] for s in subs)))
    out = k.raw("get", "secrets", "-A", "--no-headers", "-o", "custom-columns=NS:.metadata.namespace,TYPE:.type")
    if out:
        counts = {}
        for ln in out.splitlines():
            ns = ln.split()[0] if ln.split() else "?"
            counts[ns] = counts.get(ns, 0) + 1
        emit("INFO", "secrets", "Secrets per namespace (names/values not read): %s" % ", ".join("%s=%d" % kv for kv in sorted(counts.items())))


# --------------------------------------------------------------------------------------------------
def jellyfin_get(base, key, path):
    req = urllib.request.Request(base + path, headers={"Authorization": 'MediaBrowser Token="%s"' % key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def check_jellyfin(k, ns, base_override=None):
    if base_override:
        base = base_override
    else:
        ip = k.raw("-n", ns, "get", "svc", "jellyfin", "-o", "jsonpath={.spec.clusterIP}")
        if not ip:
            emit("INFO", "jellyfin", "no jellyfin service in namespace %s: skipped" % ns)
            return
        base = "http://%s:8096" % ip.strip()
    enc = k.raw("-n", ns, "get", "secret", "jellyfin-api", "-o", "jsonpath={.data.api-key}")
    if not enc:
        emit("INFO", "jellyfin", "no API key Secret yet (run make jellyfin-provision): Jellyfin's own settings were not checked")
        return
    key = base64.b64decode(enc).decode()
    try:
        net = jellyfin_get(base, key, "/System/Configuration/network")
        srv = jellyfin_get(base, key, "/System/Configuration")
        users = jellyfin_get(base, key, "/Users")
        keys = jellyfin_get(base, key, "/Auth/Keys")
        plugins = jellyfin_get(base, key, "/Plugins")
    except (urllib.error.URLError, OSError, ValueError) as e:
        emit("WARN", "jellyfin", "could not read Jellyfin's settings through its API (%s); if this follows a restore, run make jellyfin-provision" % e)
        return
    emit("INFO", "jellyfin", "remote access (outside the local network) is %s" % ("ALLOWED" if net.get("EnableRemoteAccess") else "blocked"))
    if net.get("EnableUPnP"):
        emit("WARN", "jellyfin", "UPnP is on: Jellyfin may ask the router to open ports to the internet by itself")
    else:
        emit("OK", "jellyfin", "UPnP is off")
    if net.get("AutoDiscovery"):
        emit("INFO", "jellyfin", "auto-discovery is on (answers 'who is a Jellyfin server' broadcasts on the LAN)")
    if net.get("KnownProxies"):
        emit("INFO", "jellyfin", "trusted proxies: %s" % ", ".join(net["KnownProxies"]))
    else:
        emit("INFO", "jellyfin", "no trusted proxies set: behind the ingress, every client looks like the ingress to Jellyfin (matters for login-lockout and logs)")
    if srv.get("EnableLegacyAuthorization"):
        emit("WARN", "jellyfin", "legacy authorization is on (older, weaker way for clients to send credentials)")
    if srv.get("QuickConnectAvailable"):
        emit("INFO", "jellyfin", "Quick Connect is on (log in a TV by typing a code; one more login path)")
    if srv.get("EnableMetrics"):
        emit("WARN", "jellyfin", "the /metrics endpoint is on")
    admins = [u["Name"] for u in users if (u.get("Policy") or {}).get("IsAdministrator")]
    emit("INFO", "jellyfin", "users: %s; administrators: %s" % (", ".join(u["Name"] for u in users), ", ".join(admins) or "none"))
    for u in users:
        pol = u.get("Policy") or {}
        if pol.get("LoginAttemptsBeforeLockout") == -1:
            emit("WARN", "jellyfin", "%s: failed logins never lock the account (LoginAttemptsBeforeLockout -1)" % u["Name"])
        if not u.get("HasPassword", True):
            emit("WARN", "jellyfin", "%s has no password" % u["Name"])
    emit("INFO", "jellyfin", "API keys: %s" % (", ".join(i.get("AppName", "?") for i in keys.get("Items", [])) or "none"))
    emit("INFO", "jellyfin", "plugins: %s" % (", ".join("%s %s" % (p.get("Name"), p.get("Version")) for p in plugins) or "none"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kubectl", required=True)
    ap.add_argument("--media-namespace", default="media")
    ap.add_argument("--jellyfin-url", default="")
    a = ap.parse_args()
    k = Kube(a.kubectl)
    print("== security audit (cluster)")
    if not check_nodes(k):
        return 1
    check_namespaces(k)
    check_pods(k)
    check_exposure(k)
    check_rbac(k)
    check_jellyfin(k, a.media_namespace, a.jellyfin_url or None)
    print("SUMMARY cluster: %d warnings, %d to know about, %d already good" % (COUNTS["WARN"], COUNTS["INFO"], COUNTS["OK"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
