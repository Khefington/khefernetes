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
| 2 | Hosts | key-only SSH on the VMs, host firewall (castellan + VMs), automatic security updates, Proxmox two-factor, API token privilege separation, NFS export tightened | not started |
| 3 | Edge | TLS at Traefik, Jellyfin's trusted-proxy and lockout settings | not started |
| 4 | VPN | WireGuard or Tailscale, then turn on Jellyfin's remote access | not started |

Stages 1 and 2 change how the cluster is built (RKE2 profile and encryption are chosen at install time), so they are applied with the next rebuild.

## Reading the audit
`make security-audit` prints lines like `[WARN] ssh: password login is allowed ...`.
- `[WARN]` worth fixing before outside access. `[INFO]` know about it (often expected: Kubernetes itself needs host access). `[OK]` already good.
- It reads only metadata. Secret values are never read; Jellyfin's API key is used in memory to read Jellyfin's own settings.
- Each machine ends with a `SUMMARY` line; compare runs before and after each stage.
- It cannot see your router. Check by hand that **no port forwards** exist to castellan, the VMs or `192.168.1.200` (router admin page > port forwarding / virtual servers), and that UPnP is off on the router.
