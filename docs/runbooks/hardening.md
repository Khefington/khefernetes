# Hardening before the server is reachable from outside

Goal: reach Jellyfin from outside the house over a **VPN** (smallest attack surface: nothing is published to the internet; only the VPN endpoint is reachable), and make sure that if one thing is compromised it cannot take everything with it.

## Which VPN
- **NordVPN does not fit this job.** It routes your *outgoing* traffic through Nord's servers (that is what it will do for qBittorrent later). Its remote-access feature, Meshnet, was shut down on 1 December 2025.
- For *incoming* access from your phone or laptop use a VPN you control: **WireGuard** (runs on castellan or the router, one UDP port forwarded, fully in this repo) or **Tailscale** (no port forward, easier on phones and behind carrier NAT, needs a Tailscale account). Decision pending; stage 4 needs it.

## Stages (each one verified before the next)
| # | Stage | What it covers | State |
|---|---|---|---|
| 0 | `make security-audit` | Read-only report of what is open, weak or missing | built |
| 1 | Cluster | RKE2 CIS profile + Secret encryption, pod-security labels per namespace, NetworkPolicies (default-deny in `media`), `securityContext` on every app, pinned image digests | not started |
| 2 | Hosts | host firewall (castellan + VMs), automatic security updates on castellan; then by hand: Proxmox two-factor; later: least-privilege API token | firewall + updates written (`make host-firewall`), not applied yet |
| 3 | Edge | TLS at Traefik, Jellyfin's trusted-proxy and lockout settings | not started |
| 4 | VPN | WireGuard or Tailscale, then turn on Jellyfin's remote access | not started |

Stages 1 and 2 change how the cluster is built (RKE2 profile and encryption are chosen at install time), so they are applied with the next rebuild.

## Reading the audit
`make security-audit` prints lines like `[WARN] ssh: password login is allowed ...`.
- `[WARN]` worth fixing before outside access. `[INFO]` know about it (often expected: Kubernetes itself needs host access). `[OK]` already good.
- It reads only metadata. Secret values are never read; Jellyfin's API key is used in memory to read Jellyfin's own settings.
- Each machine ends with a `SUMMARY` line; compare runs before and after each stage.
- It cannot see your router. Check by hand that **no port forwards** exist to castellan, the VMs or `192.168.1.200` (router admin page > port forwarding / virtual servers), and that UPnP is off on the router.

## First audit (12 Oct 2026) and what it means
Real findings, in the order they matter:
1. **No firewall anywhere** (castellan, all VMs). Every listening port is open to the whole LAN. Stage 2.
2. **Plain HTTP ingress.** Logins and video cross the LAN in clear text. Also the ingress answers any host name / the bare IP. Stage 3.
3. **Jellyfin:** legacy authorization is on; failed logins never lock an account (`LoginAttemptsBeforeLockout -1` means *disabled*: stored as null); Quick Connect on. Stage 3 (via `make jellyfin-provision`).
4. **RKE2:** no CIS profile, Secrets unencrypted in etcd. Stage 1.
5. **No network policies / pod-security labels** on `media` and the other app namespaces. Stage 1.
6. **Proxmox:** root@pam has no two-factor; the `Automation` API token has privilege separation off (it can do everything `ansible@pam` can). Stage 2.
7. **castellan:** 12 pending security updates and no automatic security updates; the VMs have both handled but are waiting for a reboot (the new kernel). Stage 2.

Not problems (the audit now explains them instead of flagging them): NFS and RPC helper ports (random ports are normal for mountd/statd/lockd), `udp/8472` (Canal's overlay between nodes), the DHCPv6 client, MetalLB's speaker (needs host networking), the GPU plugin (needs hostPath), local-path-provisioner, and the RKE2 `helm-*` service accounts.

## Stage 2: host firewall and updates
`make host-firewall` is a **plan**: it renders the rules for every machine, has `nft` syntax-check them, prints them and changes nothing.
`make host-firewall-apply` applies them: castellan first (plus automatic security updates), then the workers one at a time, then the control plane.

What the firewall is: one nftables table, `khef_filter`, with a single `input` chain (traffic addressed TO the machine). Forwarded traffic (pods, VMs, the ingress address 192.168.1.200) is not touched.
- Everywhere: loopback, replies to connections the machine started, ping, IPv6 neighbour discovery, DHCP answers, and SSH from the LAN.
- castellan also: Proxmox web UI and SPICE (8006, 3128) from the LAN; NFS (2049, version 4 only, so that single port) from the three VMs; DNS (53) from the LAN.
- VMs also: everything from the other nodes and from the pod and service networks (10.42.0.0/16, 10.43.0.0/16).
- Everything else is dropped; a few refused packets per minute are logged (`journalctl -k | grep khef-fw`).
Tighten later with `host_firewall_admin_cidrs: [192.168.1.20/32]` (your PC with a fixed address) once you want only it to reach SSH and the Proxmox UI.

**Safety.** Before the rules are loaded on a machine, a one-off timer is armed that removes them after 3 minutes. The playbook then opens a NEW SSH connection from your PC (and the Proxmox UI on castellan); only if that works does it cancel the timer and make the rules permanent (`khef-firewall.service`). If you lose contact, wait 3 minutes and the rules are gone. Emergency off any time: `make host-firewall-off`, or `systemctl stop khef-firewall` on the machine's console.
After the VMs: every node must be Ready and the NFS port on castellan reachable from the cluster, or the playbook stops.

**Updates.** `unattended-upgrades` on castellan installs Debian security updates by itself. Proxmox packages and kernels stay manual (a Proxmox upgrade can need a reboot, which takes every VM down). It never reboots.

## Your router and UPnP
- Jellyfin's own UPnP is off (the audit confirms). But UPnP on the router lets *any* device on the LAN ask for a port to the internet, including a compromised pod or VM. The host firewall does not stop that (it filters what reaches the machine, not what the machine asks the router for).
- With a VPN you need at most **one** forwarded UDP port (WireGuard) or none (Tailscale), so UPnP gives an attacker the only extra way in.
- Keep UPnP on for your PC if you want, and check what it has opened: the gFiber app (Network > Port forwarding / Advanced) lists mappings. Anything you do not recognise: remove it.
- Real separation comes from a second router for the lab (the lab network sits behind it; your PC and UPnP stay on the gFiber side). Google's own page says bridge mode "turns off your gFiber router's Wi-Fi and routing" so your router does the routing ([gFiber: bridge mode](https://gfiber.com/support/en/answer/1924/)); gFiber also says most customers do not need it and can plug their own router into the Fiber Jack ([gFiber: your own router](https://gfiber.com/support/en/answer/1816/)). Bridge mode alone does not isolate anything; the isolation is having a separate router with its own subnet. That means re-addressing every machine (castellan, VMs, MetalLB range, DNS), so it is a project of its own, not a prerequisite for the VPN.
