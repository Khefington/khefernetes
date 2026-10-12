# Khefernetes

A home media server, fully automated with Ansible and rebuildable from Git:
Proxmox host (castellan) -> 3 Ubuntu VMs -> RKE2 Kubernetes -> Jellyfin, with the library on the host's HDD shared over NFS.

## Quick start

```
make setup && source .venv/bin/activate     # Python packages + Ansible collections
echo '<vault password>' > .vault_pass       # git-ignored; see docs/secrets.md
make ping                                   # can Ansible reach everything?
make site                                   # the whole build, in order
```
`make help` lists every target.

## Everyday tasks

| Task | Command |
|---|---|
| Copy media from the Windows PC | `make import-media` |
| Prove nothing is missing | `make audit-media` |
| Fix media copied one folder too deep | `make flatten-media` then `make flatten-media APPLY=1` |
| Jellyfin trickplay / file-access problems | `make diagnose-jellyfin` |
| Back up Jellyfin now | `make backup-now` |
| Plan Quick Sync (Intel iGPU) for Jellyfin | `make gpu-discover` (read-only), then `make gpu-host` (stage 1: plan, then apply), see `docs/runbooks/gpu-passthrough.md` |
| Look inside a Jellyfin backup zip | `python3 scripts/inspect-jellyfin-backup.py <zip>` |
| Make `jellyfin.home.lan` work on every device | `make dns`, then set the router DNS to castellan (`docs/runbooks/dns.md`) |
| Add a library (e.g. audiobooks) | add it to `media_libraries`, then `make nfs` |
| Bump a version | edit `inventories/group_vars/all/versions.yml`, run the matching target |
| Lint everything | `make lint` |

## Layout

```
inventories/   hosts + all site-specific values (group_vars/, host_vars/)
playbooks/                site.yml, one playbook per stage, operations/ for day-2 tasks
roles/                    all the logic; playbooks only pick hosts and roles
docs/                     architecture, storage, secrets, rebuild, runbooks, migration
scripts/                  helper scripts
```
Details: [docs/architecture.md](docs/architecture.md). Storage and large-library guidance: [docs/storage.md](docs/storage.md).

## Documentation

- [Architecture and design rules](docs/architecture.md)
- [Storage, hardlinks, books, large libraries](docs/storage.md)
- [Networking: MetalLB and the ingress](docs/networking.md)
- [Names on the LAN: DNS server on castellan](docs/runbooks/dns.md)
- [Secrets](docs/secrets.md)
- [Rebuild / restore drill](docs/rebuild.md)
- Runbooks: [etcd snapshots and restore](docs/runbooks/etcd-restore.md), [import media](docs/runbooks/import-media.md), [Jellyfin as code](docs/runbooks/jellyfin-provision.md), [Jellyfin backup](docs/runbooks/jellyfin-backup.md), [sizing](docs/sizing.md), [trickplay](docs/runbooks/jellyfin-trickplay.md)
- [Migrating from the old layout](docs/MIGRATION.md)
- [Ansible variable precedence cheat sheet](docs/ansible-precedence.md)
- [Dev log](docs/devlog.md)

## Roadmap
Switch the ingress to Traefik at the next rebuild (`ingress_controller`);
qBittorrent behind NordVPN using the 2TB SSD for incomplete downloads; a destroy-and-rebuild test with a Jellyfin restore drill.
