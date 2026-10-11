# Networking: MetalLB and the ingress

## What each piece does
| Piece | Job |
|---|---|
| RKE2's ingress controller (ingress-nginx or Traefik) | Receives HTTP on port 80/443 and routes by hostname to the right Service (for example Jellyfin) |
| MetalLB (layer 2) | Gives a Kubernetes `LoadBalancer` Service a real address on your LAN, from a reserved range |
| `ingress_vip` | The one address the ingress answers on. Point your DNS name at it |

Without MetalLB, the ingress only answers on each node's own address (`http://192.168.1.52`), so the address you use depends on which node is alive.
With it, one node at a time answers for `ingress_vip` and another takes over if it fails.
The node addresses keep working as well.

## Where the settings are
| Setting | File |
|---|---|
| `metallb_range` (reserved addresses, must be outside the router's DHCP pool) | `inventories/group_vars/all/main.yml` |
| `metallb_version`, `metallb_sha256` | `inventories/group_vars/all/versions.yml` |
| `ingress_controller`, `ingress_vip`, `ingress_class_name` | `inventories/group_vars/anvil_cluster/kubernetes.yml` |

## Run it
```
make networking
```
It installs MetalLB, creates the address pool, gives the ingress controller a `LoadBalancer` Service on `ingress_vip`, and then asks the ingress for a page
from a worker node using only that address. Re-running is safe.

Then make your router (or Pi-hole) resolve `jellyfin.<lan_domain>` (default `jellyfin.home.lan`) to `ingress_vip`. Ansible cannot do that step.

## Keeping the addresses from being handed to something else
Your router's DHCP server hands addresses to devices that ask for one. These machines do not ask, so the router cannot move them:
- The three VMs get fixed addresses from cloud-init (`ip=192.168.1.5x/24` in `roles/proxmox_vms`).
- castellan's address is written on the host itself (Proxmox requires a static address; it is in `/etc/network/interfaces` under `vmbr0`).
- MetalLB addresses are claimed by announcing them on the network, not by asking the router.

The only risk is the opposite one: the router giving the same address to some other device (a phone, a TV), which causes an address conflict.
Prevent it by keeping every fixed address **outside the router's DHCP range**:
- `192.168.1.50-53` for castellan and the VMs
- `192.168.1.200-220` for MetalLB (`metallb_range`)

Check the range in your router settings (exact menu names differ by router model and app). If the router will not let you shrink the range,
add a reservation for each of `.50-.53` (a reservation ties an address to a device's MAC address), and move `metallb_range` and `ingress_vip` to addresses the range does not cover.
Current setup: the router's DHCP range is `192.168.1.100-150`, so `.50-.53`, `.200-.220` and the router at `.1` are all outside it.
Change this note if you change the range.
To confirm castellan is static: `grep -A6 'iface vmbr0' /etc/network/interfaces` should show `inet static` and `address 192.168.1.50/24`.

## Check it by hand (on kasrkin)
```
kubectl -n metallb-system get pods                 # controller + one speaker per node, all Running
kubectl get svc -A | grep LoadBalancer             # EXTERNAL-IP should be the ingress_vip
kubectl get ingress -A                             # ADDRESS column shows the same IP
```
From your PC: `curl -i -H "Host: jellyfin.home.lan" http://192.168.1.200/health` should print `Healthy`.

## Switching to Traefik
`ingress-nginx` is what RKE2 v1.35 ships, but the upstream project reached end of life in March 2026, and RKE2 makes Traefik the default from v1.36.
The `ingress_controller` setting is written into RKE2's config when the server is installed, so the clean way to switch is at a rebuild:
1. Set `ingress_controller: traefik` in `kubernetes.yml`.
2. Rebuild as in `docs/rebuild.md` (`make vms nfs rke2 networking ...`).
3. `ingress_class_name` follows automatically (`nginx` becomes `traefik`), so the Jellyfin Ingress is created with the right class.

Notes:
- The Traefik branch is written from the RKE2 chart's defaults (host ports 80/443, `ClusterIP` Service, class `traefik`). It has not run on the real cluster yet, so verify it at the first rebuild.
- Switching a live cluster is possible but is a four-phase migration with both controllers side by side: <https://docs.rke2.io/reference/ingress_migration>.
- Running `make rke2` on the live cluster now would add `ingress-controller: [ingress-nginx]` to RKE2's config and restart the server. That is harmless, but wait for the rebuild anyway because of the new RKE2 token.

## Good to know
- With `externalTrafficPolicy: Local`, Jellyfin sees the real client address, and only nodes that run a controller pod answer for the address. Both controllers run on every node here.
- The first `make networking` rolls the ingress pods one node at a time (the Service and `publishService` setting change). Expect a few seconds of interruption per node.
- Other apps that need a LAN address (for example a future qBittorrent web UI) can request one with the annotation `metallb.io/loadBalancerIPs: <address>` on a `LoadBalancer` Service.
