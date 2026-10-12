#!/usr/bin/env python3
"""READ-ONLY security audit of one machine (castellan or a cluster VM). Changes nothing.

Run on the machine as root (the playbook does that):  python3 host_audit.py [--kind proxmox|node]

Prints one line per finding:   [OK] / [INFO] / [WARN]  topic: message
and a SUMMARY line at the end. [WARN] means "worth fixing before the server is reachable from outside";
[INFO] means "know about it"; [OK] means "already good". Standard library only.
"""
import glob
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys

COUNTS = {"OK": 0, "INFO": 0, "WARN": 0}


def emit(level, topic, msg):
    COUNTS[level] += 1
    print("[%s] %s: %s" % (level, topic, msg))


def run(cmd, timeout=30):
    """Run a command (list), return (returncode, stdout). Never raises."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def read(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# --------------------------------------------------------------------------------------------------
# 1. What is listening, and on which addresses
# --------------------------------------------------------------------------------------------------
# process name -> what it is. Anything listening on the network that is not in here is flagged.
KNOWN_LISTENERS = {
    "sshd": "SSH",
    "pveproxy": "Proxmox web UI / API (port 8006)",
    "spiceproxy": "Proxmox SPICE console proxy",
    "rpcbind": "NFS helper (rpcbind)",
    "rpc.mountd": "NFS server (mountd)",
    "rpc.statd": "NFS (statd)",
    "dnsmasq": "DNS server (make dns)",
    "rke2": "RKE2 (API, supervisor, embedded components)",
    "kube-apiserver": "Kubernetes API server",
    "kubelet": "kubelet",
    "kube-proxy": "kube-proxy",
    "etcd": "etcd",
    "kube-controller": "Kubernetes controller manager",
    "kube-scheduler": "Kubernetes scheduler",
    "containerd": "container runtime",
    "calico-node": "Canal / Calico networking",
    "flanneld": "Canal / flannel networking",
    "speaker": "MetalLB speaker (announces the ingress address)",
    "chronyd": "time sync (chrony)",
    "systemd-resolve": "local DNS stub",
    "systemd-timesyn": "time sync",
    "master": "mail (postfix, local delivery)",
    "pvedaemon": "Proxmox daemon",
    "pmxcfs": "Proxmox cluster filesystem",
}
# Kernel services have no process name in `ss`; recognise them by port.
KNOWN_PORTS = {"2049": "NFS server (kernel)", "111": "NFS helper (rpcbind)", "20048": "NFS server (mountd)"}
LOOPBACK = ("127.", "::1")


def parse_ss():
    rc, out = run(["ss", "-H", "-tulnp"])
    rows = []
    if rc != 0:
        return rows
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local = parts[0], parts[4]
        addr, _, port = local.rpartition(":")
        addr = addr.strip("[]")
        m = re.search(r'\(\("([^"]+)"', line)
        rows.append({"proto": proto, "addr": addr, "port": port, "proc": m.group(1) if m else "?"})
    return rows


def check_listeners():
    rows = parse_ss()
    if not rows:
        emit("INFO", "listeners", "could not read the socket list (is `ss` installed and are you root?)")
        return
    exposed = {}
    local_only = 0
    for r in rows:
        if r["addr"].startswith(LOOPBACK):
            local_only += 1
            continue
        key = (r["proc"], r["proto"], r["port"])
        exposed.setdefault(key, set()).add(r["addr"])
    emit("INFO", "listeners", "%d sockets are bound to localhost only (not reachable from the network); %d are reachable from the network" % (local_only, len(exposed)))
    for (proc, proto, port), addrs in sorted(exposed.items(), key=lambda kv: (kv[0][0], kv[0][1], int(kv[0][2]) if kv[0][2].isdigit() else 0)):
        where = "all interfaces" if addrs & {"0.0.0.0", "::", "*"} else ", ".join(sorted(addrs))
        what = next((v for k, v in KNOWN_LISTENERS.items() if proc.startswith(k)), None) or (KNOWN_PORTS.get(port) if proc == "?" else None)
        if what:
            emit("INFO", "listeners", "%s/%s (%s) on %s: %s" % (proto, port, proc, where, what))
        else:
            emit("WARN", "listeners", "%s/%s (%s) on %s: not one of the services this setup expects. Find out what it is" % (proto, port, proc, where))


# --------------------------------------------------------------------------------------------------
# 2. SSH
# --------------------------------------------------------------------------------------------------
def check_ssh():
    sshd = shutil.which("sshd") or "/usr/sbin/sshd"
    rc, out = run([sshd, "-T"])
    if rc != 0:
        emit("INFO", "ssh", "could not read the effective sshd settings (`sshd -T` failed)")
        return
    cfg = {}
    for line in out.splitlines():
        k, _, v = line.partition(" ")
        cfg.setdefault(k.lower(), v.strip())
    pra = cfg.get("permitrootlogin", "?")
    if pra == "yes":
        emit("WARN", "ssh", "root can log in with a password (PermitRootLogin yes)")
    elif pra in ("prohibit-password", "without-password"):
        emit("OK", "ssh", "root can only log in with a key (PermitRootLogin %s)" % pra)
    else:
        emit("OK", "ssh", "PermitRootLogin %s" % pra)
    for key, label in (("passwordauthentication", "password login"), ("kbdinteractiveauthentication", "keyboard-interactive login")):
        if cfg.get(key) == "yes":
            emit("WARN", "ssh", "%s is allowed (%s yes): anyone on the network can try passwords" % (label, key))
        else:
            emit("OK", "ssh", "%s is off" % label)
    if cfg.get("pubkeyauthentication") == "no":
        emit("WARN", "ssh", "key login is switched off")
    try:
        tries = int(cfg.get("maxauthtries", "6"))
    except ValueError:
        tries = 6
    if tries > 4:
        emit("INFO", "ssh", "MaxAuthTries is %d (4 or fewer slows password guessing; matters little when passwords are off)" % tries)
    if cfg.get("x11forwarding") == "yes":
        emit("INFO", "ssh", "X11 forwarding is on (not needed on a server)")
    if cfg.get("permitemptypasswords") == "yes":
        emit("WARN", "ssh", "empty passwords are accepted")


# --------------------------------------------------------------------------------------------------
# 3. Host firewall
# --------------------------------------------------------------------------------------------------
def check_firewall(kind):
    active = False
    if shutil.which("pve-firewall"):
        rc, out = run(["pve-firewall", "status"])
        txt = out.strip().replace("\n", " ")
        if "enabled/running" in txt:
            emit("OK", "firewall", "Proxmox firewall is on (%s)" % txt)
            active = True
        else:
            emit("WARN", "firewall", "Proxmox firewall is off (%s)" % (txt or "no answer"))
    if shutil.which("ufw"):
        rc, out = run(["ufw", "status"])
        if "Status: active" in out:
            emit("OK", "firewall", "ufw is active")
            active = True
        else:
            emit("INFO", "firewall", "ufw is installed but not active")
    for tool in ("iptables", "ip6tables"):
        if shutil.which(tool):
            rc, out = run([tool, "-S", "INPUT"])
            first = out.splitlines()[0] if out.strip() else ""
            if first.startswith("-P INPUT DROP"):
                emit("OK", "firewall", "%s INPUT policy is DROP" % tool)
                active = True
            elif first:
                emit("INFO", "firewall", "%s INPUT policy: %s" % (tool, first.replace("-P INPUT ", "")))
    if not active:
        emit("WARN", "firewall", "no host firewall is filtering incoming traffic: every listening port above is open to anything that can reach this machine")


# --------------------------------------------------------------------------------------------------
# 4. Patching
# --------------------------------------------------------------------------------------------------
def check_updates():
    rc, out = run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"], timeout=90)
    inst = [ln for ln in out.splitlines() if ln.startswith("Inst ")]
    sec = [ln for ln in inst if "-security" in ln or "Security" in ln]
    if rc == 0:
        if not inst:
            emit("OK", "updates", "no pending package updates (as of the last `apt update`)")
        else:
            level = "WARN" if sec else "INFO"
            emit(level, "updates", "%d packages can be updated, %d of them security updates (as of the last `apt update`)" % (len(inst), len(sec)))
    unattended = False
    if shutil.which("dpkg"):
        rc, out = run(["dpkg", "-s", "unattended-upgrades"])
        unattended = rc == 0 and "Status: install ok installed" in out
    auto = read("/etc/apt/apt.conf.d/20auto-upgrades")
    if unattended and re.search(r'Unattended-Upgrade\s+"1"', auto):
        emit("OK", "updates", "unattended-upgrades installs security updates automatically")
    elif unattended:
        emit("WARN", "updates", "unattended-upgrades is installed but not enabled in 20auto-upgrades")
    else:
        emit("WARN", "updates", "no automatic security updates (unattended-upgrades is not installed)")
    if os.path.exists("/var/run/reboot-required"):
        emit("WARN", "updates", "a reboot is pending (/var/run/reboot-required)")


# --------------------------------------------------------------------------------------------------
# 5. Accounts
# --------------------------------------------------------------------------------------------------
def check_accounts():
    login = []
    for line in read("/etc/passwd").splitlines():
        f = line.split(":")
        if len(f) < 7:
            continue
        name, uid, shell = f[0], int(f[2]) if f[2].isdigit() else -1, f[6]
        if uid == 0 and name != "root":
            emit("WARN", "accounts", "'%s' has uid 0 (root powers)" % name)
        if shell not in ("/usr/sbin/nologin", "/bin/false", "/sbin/nologin", "/usr/bin/false", "") and (uid >= 1000 or name == "root"):
            login.append((name, f[5]))
    emit("INFO", "accounts", "accounts that can log in: %s" % ", ".join(n for n, _ in login))
    for line in read("/etc/shadow").splitlines():
        f = line.split(":")
        if len(f) > 1 and f[1] == "":
            emit("WARN", "accounts", "'%s' has an empty password" % f[0])
    for name, home in login:
        ak = os.path.join(home, ".ssh", "authorized_keys")
        keys = [ln for ln in read(ak).splitlines() if ln.strip() and not ln.startswith("#")]
        if keys:
            emit("INFO", "accounts", "%s has %d authorized SSH key(s)" % (name, len(keys)))
    nopasswd = []
    for path in ["/etc/sudoers"] + sorted(glob.glob("/etc/sudoers.d/*")):
        for ln in read(path).splitlines():
            if "NOPASSWD" in ln and not ln.strip().startswith("#"):
                nopasswd.append("%s: %s" % (os.path.basename(path), ln.strip()))
    if nopasswd:
        emit("INFO", "accounts", "passwordless sudo: %s" % "; ".join(nopasswd))


# --------------------------------------------------------------------------------------------------
# 6. Proxmox specifics
# --------------------------------------------------------------------------------------------------
def pvesh(path):
    rc, out = run(["pvesh", "get", path, "--output-format", "json"])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def check_proxmox():
    users = pvesh("/access/users")
    if users is None:
        emit("INFO", "proxmox", "could not read Proxmox users (pvesh failed)")
    else:
        emit("INFO", "proxmox", "users: %s" % ", ".join("%s%s" % (u.get("userid"), "" if u.get("enable", 1) else " (disabled)") for u in users))
        tfa = pvesh("/access/tfa") or []
        with_tfa = {t.get("userid") for t in tfa if t.get("entries")}
        if "root@pam" in with_tfa:
            emit("OK", "proxmox", "root@pam has two-factor login")
        else:
            emit("WARN", "proxmox", "root@pam has no two-factor login (the web UI on 8006 accepts the Linux root password)")
        for u in users:
            uid = u.get("userid")
            toks = pvesh("/access/users/%s/token" % uid) or []
            for t in toks:
                priv = t.get("privsep", 1)
                if str(priv) in ("0", "False", "false"):
                    emit("WARN", "proxmox", "API token %s!%s has privilege separation OFF: it can do everything %s can" % (uid, t.get("tokenid"), uid))
                else:
                    emit("INFO", "proxmox", "API token %s!%s (privilege separation on)" % (uid, t.get("tokenid")))
    acl = pvesh("/access/acl")
    if acl:
        broad = [a for a in acl if a.get("path") == "/" and a.get("roleid") == "Administrator"]
        for a in broad:
            emit("INFO", "proxmox", "Administrator on '/' is granted to %s %s" % (a.get("type"), a.get("ugid")))
    # NFS exports: who may mount the library?
    exports = []
    for path in ["/etc/exports"] + sorted(glob.glob("/etc/exports.d/*.exports")):
        for ln in read(path).splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                exports.append(ln)
    for ln in exports:
        for host, opts in re.findall(r'(\S+?)\(([^)]*)\)', ln):
            problems = []
            if host in ("*", ""):
                problems.append("any machine may mount it")
            else:
                try:
                    net = ipaddress.ip_network(host, strict=False)
                    if net.prefixlen < 24:
                        problems.append("a wide network (/%d) may mount it" % net.prefixlen)
                except ValueError:
                    pass
            if "no_root_squash" in opts:
                problems.append("no_root_squash: a client's root is root on the disk")
            if problems:
                emit("WARN", "nfs", "%s -> %s(%s): %s" % (ln.split()[0], host, opts, "; ".join(problems)))
            else:
                emit("INFO", "nfs", "%s -> %s (%s)" % (ln.split()[0], host, opts))
    if not exports:
        emit("INFO", "nfs", "no NFS exports found")


# --------------------------------------------------------------------------------------------------
# 7. RKE2 specifics (on cluster VMs)
# --------------------------------------------------------------------------------------------------
def check_rke2():
    cfg_path = "/etc/rancher/rke2/config.yaml"
    if not os.path.exists(cfg_path):
        return
    cfg = read(cfg_path)
    is_server = os.path.exists("/etc/rancher/rke2/rke2.yaml") or "tls-san" in cfg
    if re.search(r'^profile:\s*\S+', cfg, re.M):
        emit("OK", "rke2", "CIS hardening profile is set (%s)" % re.search(r'^profile:\s*(\S+)', cfg, re.M).group(1))
    else:
        emit("WARN", "rke2", "no CIS hardening profile (`profile: cis` in config.yaml): RKE2's own hardening switches are off")
    if is_server:
        if re.search(r'^secrets-encryption:\s*true', cfg, re.M):
            emit("OK", "rke2", "Kubernetes Secrets are encrypted in etcd")
        else:
            emit("WARN", "rke2", "Secrets are stored unencrypted in etcd (`secrets-encryption: true` is not set)")
        for path in ("/etc/rancher/rke2/rke2.yaml", "/var/lib/rancher/rke2/server/token", "/var/lib/rancher/rke2/server/node-token"):
            if os.path.exists(path):
                mode = oct(os.stat(path).st_mode & 0o777)
                if os.stat(path).st_mode & 0o077:
                    emit("WARN", "rke2", "%s is readable by other users (mode %s)" % (path, mode))
                else:
                    emit("OK", "rke2", "%s is private (mode %s)" % (path, mode))
    if re.search(r'^protect-kernel-defaults:\s*true', cfg, re.M):
        emit("OK", "rke2", "protect-kernel-defaults is on")


def main():
    kind = "node"
    if "--kind" in sys.argv:
        kind = sys.argv[sys.argv.index("--kind") + 1]
    print("== security audit (%s) on %s" % (kind, os.uname()[1]))
    check_listeners()
    check_ssh()
    check_firewall(kind)
    check_updates()
    check_accounts()
    if kind == "proxmox":
        check_proxmox()
    else:
        check_rke2()
    print("SUMMARY %s: %d warnings, %d to know about, %d already good" % (os.uname()[1], COUNTS["WARN"], COUNTS["INFO"], COUNTS["OK"]))


if __name__ == "__main__":
    main()
