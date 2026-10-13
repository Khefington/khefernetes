# Hardening before the server is reachable from outside

Goal: reach Jellyfin from outside the house over a **VPN** (smallest attack surface: nothing is published to the internet; only the VPN endpoint is reachable), and make sure that if one thing is compromised it cannot take everything with it.

## Which VPN
- **NordVPN does not fit this job.** It routes your *outgoing* traffic through Nord's servers (that is what it will do for qBittorrent later). Its remote-access feature, Meshnet, was shut down on 1 December 2025.
- For *incoming* access from your phone or laptop use a VPN you control. **Decision: WireGuard on castellan** (one UDP port forwarded, fully in this repo, no account). Tailscale (no port forward, needs an account) stays the alternative if the port forward ever turns out not to work.

## Stages (each one verified before the next)
| # | Stage | What it covers | State |
|---|---|---|---|
| 0 | `make security-audit` | Read-only report of what is open, weak or missing | built |
| 1 | Cluster | pod-security labels per namespace, NetworkPolicies (default-deny in `media`) | written (`make cluster-hardening`), not applied yet |
| 1b | Cluster, install-time | RKE2 CIS profile + Secret encryption, image digests | deferred to a drill rebuild (see below) |
| 2 | Hosts | host firewall (castellan + VMs), automatic security updates on castellan; then by hand: Proxmox two-factor; later: least-privilege API token | firewall + updates written (`make host-firewall`), not applied yet |
| 3 | Edge | Jellyfin lockout + legacy authorization off (done, `make jellyfin-provision`); TLS at Traefik (deferred, see below) | settings written; TLS deferred |
| 4 | VPN | WireGuard on castellan (`make wireguard`), devices with `make wireguard-client PEER=...` | written, not applied yet |

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

## Stage 1: pod security and network policies
`make cluster-hardening` is a **plan**: it asks the API server (dry run) what the labels and policies would do and prints it; nothing changes.
`make cluster-hardening-apply` applies them, then **proves** the result from the inside and the outside, and removes the policies again by itself if a critical proof fails.
`make cluster-hardening-off` removes the policies by hand.

**Pod-security levels** (Kubernetes' built-in admission; a namespace's pods must meet the level or are refused):
| Namespace | Level | Why |
|---|---|---|
| `media` | enforce `baseline`, audit `restricted` | Jellyfin's start-up helper runs as root to fix ownership, so `restricted` is not possible yet; `audit` records what stops us. No privileged containers, host networking or hostPath here. |
| `downloads` | `privileged` (explicit) | Gluetun (the VPN client in qBittorrent's pod) needs `NET_ADMIN` and the tun device, which `baseline` forbids. Only that namespace gets this, and it is sealed by its own policies (below). |
| `intel-gpu-plugin`, `local-path-storage`, `metallb-system` | `privileged` (explicit) | They need host access by design. Written down instead of left implicit. |

**NetworkPolicies in `media`** (Canal enforces them): default-deny for every pod, then only:
- DNS to CoreDNS.
- Into Jellyfin (8096): the ingress controller, the backup job, and the cluster's own nodes (so restore / profile-fix / the audit keep working).
- Out of Jellyfin: the internet on 80/443 only, **not** your LAN (router, castellan, the Proxmox UI), not other pods.
- The backup job: only to Jellyfin.
Download stack (when `arr_enabled` and the `downloads` namespace exists): Sonarr, Radarr and Prowlarr may be reached by the ingress controller, each other, the backup job and the nodes; they may go out to the internet on 80/443, to each other and to qBittorrent on 8080, not to your LAN. The backup job reaches only the three apps.
`downloads` is **sealed**: default-deny both ways; qBittorrent's web port (8080) is reachable from the ingress controller, the three apps and the nodes; and it may send only UDP 51820 to non-private addresses, which is the WireGuard tunnel to NordVPN (no DNS to the cluster, no LAN, no other pods). That is the second lock under Gluetun's own firewall.
Adding another app later: its pods are denied everything until its own policy is added next to these; copy a `jellyfin-*` or `arr-*` block.

**The proofs after applying:** (critical, roll back if they fail) the web through 192.168.1.200 answers; the control plane can reach Jellyfin directly; Jellyfin can resolve names and reach the internet; the backup job's path works. (reported) Jellyfin must NOT reach 192.168.1.1 or castellan:8006; a pod in another namespace must NOT reach Jellyfin. A `[WARN] ... CAN reach` there means the policy is not being enforced.

### Stage 1b, deferred on purpose: RKE2 CIS profile and Secret encryption
Both are chosen when RKE2 is installed, so they belong in a rebuild drill (the one after tomorrow's), not on the running cluster, and I have not been able to test them:
- `profile: cis` makes RKE2 enforce the `restricted` pod-security level cluster-wide (our labelled namespaces override it), needs an `etcd` system user and a few kernel settings on the nodes, and installs default network policies in the system namespaces.
- `secrets-encryption: true` encrypts Secrets in etcd. The open question to settle first: whether an etcd snapshot restore onto a rebuilt cluster still decrypts them (the encryption keys have to come along). That belongs in the etcd restore drill (`docs/runbooks/etcd-restore.md`).
- Image digests (not just tags) need a step that resolves and records them.

## Stage 3 (settings): Jellyfin lockout and legacy authorization
`make jellyfin-provision` now also sets (in `inventories/group_vars/all/jellyfin.yml`):
- `EnableLegacyAuthorization: false`: Jellyfin refuses the old way of sending credentials (`X-Emby-*` headers, `?api_key=` in a URL). Current apps use the `Authorization: MediaBrowser ...` header. Everything in this repo does. If an old client stops signing in, set it back to `true` and re-run.
- `jellyfin_user_lockout_attempts: 5`: five failed logins in a row lock the account (before: never). A locked account is just "disabled", and **every provisioning run sets the accounts listed in `jellyfin_users` enabled again with the counter at 0**, so the admin can never be locked out for good: `make jellyfin-provision` is the way back in (it uses the API key, not a password).
Left alone on purpose: Quick Connect (handy for TVs; it needs an already signed-in device to approve the code) and trusted proxies.

**TLS at the ingress is deferred.** Over the VPN everything is already encrypted end to end (the WireGuard tunnel), so plain `http://jellyfin.home.lan` is safe from outside. On the home LAN it is still clear text; fixing that needs certificates your TVs and phones trust (a private CA on every device, or a real domain name plus a Let's Encrypt DNS challenge). Revisit if you own a domain.

## Stage 4: remote access with WireGuard
**What it is.** castellan runs a WireGuard server (`wg0`, network `10.8.0.0/24`, castellan is `10.8.0.1`). Your phone gets a private key and the server's public key; castellan only accepts devices it has a key for. To anyone else the UDP port is silent: no reply, no banner, nothing to probe.
**What a device can reach**, set per device in `inventories/group_vars/all/wireguard.yml`:
| `access` | Reaches | Use for |
|---|---|---|
| `jellyfin` | Only the ingress address (`192.168.1.200`) on 80/443, plus DNS from castellan. Nothing else on the LAN, no internet through you. | phones, tablets, family |
| `lan` | The whole LAN and castellan's admin ports, like a PC at home. | your own laptop |
Mechanically: the firewall's `forward` chain only looks at traffic from or to `wg0` (VM and pod traffic is untouched), and VPN traffic leaves castellan with castellan's own address (NAT), so nothing else on the LAN needs a new route.
**Split tunnel.** A device sends only Jellyfin (and DNS) through the tunnel; the rest of its traffic keeps its normal route. Your phone's other apps are not slowed down and are not sent through your house.
**DNS.** Devices use castellan (`10.8.0.1`) for DNS, so `jellyfin.home.lan` works from anywhere. (dnsmasq also listens on `10.8.0.1`; `bind-dynamic` lets it start before the tunnel exists.)

### Set it up (once)
1. `make host-firewall-apply` (opens UDP 51820 and adds the VPN filtering; the usual timed rollback applies).
2. `make wireguard`. Installs WireGuard, makes the server key and one key + preshared key per device **on castellan** (`/etc/wireguard`, root only; nothing secret goes into the repo) and starts the tunnel.
3. **By hand, once:** in the Google Fiber app, forward **UDP 51820** to castellan (`192.168.1.50`). (This is the one mapping to allow; UPnP can stay on for your PC.)
4. Decide how devices find your home: a DDNS name (see "A home address that changes" below; recommended), a fixed address in `wireguard_endpoint`, or nothing. If you leave both empty, `make wireguard-client` looks up your current public address and uses it, which breaks when the provider changes it.
5. `make wireguard-client PEER=phone`: prints the device's file and a QR code. In the WireGuard app: **+ > Scan from QR code**. Press Enter, clear the terminal (the output contains the device's private key).
6. Turn Wi-Fi off on the phone and open `http://jellyfin.home.lan` in the Jellyfin app (server address) or the browser. It works if the tunnel is up and the sign-in page loads.

### Daily use
- Add a device: add a line to `wireguard_peers` (new name, next free `10.8.0.x`), `make wireguard`, `make wireguard-client PEER=<name>`. The running tunnel is updated without dropping other devices.
- Remove a device: delete its line, `make wireguard`. (Its key stays on castellan until you delete `/etc/wireguard/peers/<name>.*`; do not reuse its address for someone else.)
- A lost phone: remove its line and `make wireguard`; the key stops working at once.
- Emergency off: `make wireguard-off`. The LAN is unaffected.
- `make security-audit` reports the tunnel, how many devices have ever connected, and whether the VPN filtering is loaded.
- Jellyfin's `EnableRemoteAccess` can stay off: VPN traffic reaches Jellyfin from castellan's LAN address, which Jellyfin treats as local.
- **If castellan is reinstalled** the keys are gone: every device needs a new file (`make wireguard-client`). Back up `/etc/wireguard` if that would be painful.

### Known limits
- Plain HTTP over the tunnel (already encrypted), but anyone who gets *into* the tunnel as a `lan` device can reach the whole LAN: give `lan` only to your own machines.
- The home public address must be reachable: carrier-grade NAT or an ISP that blocks inbound UDP would break the port forward (Tailscale is the fallback).
- Google Fiber's router may reset a port forward after a router reset or firmware change; if the phone stops connecting from outside, check the forward first.

### A home address that changes: DuckDNS
Your phone's file names where to connect. A name that always points at your current home address keeps it working when Google Fiber changes the address.
**By hand, once:** sign in at <https://www.duckdns.org> (it uses a Google/GitHub/etc. login), create a name (for example `khef-home`), and copy the token from the top of the page.
1. `ansible-vault edit inventories/group_vars/all/vault.yml` and add `vault_duckdns_token: "<the token>"`.
2. In `inventories/group_vars/all/ddns.yml` set `ddns_duckdns_subdomain: khef-home` (just the first part).
3. `make ddns`. It puts the token in a root-only file on castellan, installs a systemd timer that tells DuckDNS your current IPv4 address every 5 minutes (and 2 minutes after a boot), updates once right away and checks that `khef-home.duckdns.org` now resolves to that address.
4. `wireguard_endpoint` becomes `khef-home.duckdns.org` by itself. A phone you already set up: open the tunnel in the WireGuard app > Edit > Peer > Endpoint > `khef-home.duckdns.org:51820` (or re-issue it with `make wireguard-client PEER=phone`).
`make ddns-status` shows the last updates. Wrong token or name: the update fails with a clear message in that log (`DuckDNS refused the update`).
Notes:
- The name publishes your home IP address in DNS. Anything you connect to already sees that address, and the only thing listening there is the silent WireGuard port, so this adds little. Do not point DuckDNS at services you have not hardened.
- The WireGuard apps look the name up each time the tunnel is switched on. After an address change, switch the tunnel off and on once.
- The updater only reports IPv4 (`curl -4`): the port forward is IPv4. IPv6-only mobile networks still reach an IPv4 address through the carrier's translation.
- The token is a secret: in the vault, and on castellan only in `/etc/khefernetes/ddns.env` (mode 0600). It is passed to curl on stdin so it does not appear in the process list.
