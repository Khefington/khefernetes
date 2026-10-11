# Architecture

## Hosts

| Name | Role | Address | Notes |
|---|---|---|---|
| castellan | Proxmox VE host | 192.168.1.50 | NFS server, owns all disks |
| kasrkin | RKE2 control plane (VM 201) | 192.168.1.51 | kubectl runs here, never on the home PC |
| wyvern | RKE2 worker (VM 202) | 192.168.1.52 | |
| basilisk | RKE2 worker (VM 203) | 192.168.1.53 | |

Disks on castellan: 1TB SSD (Proxmox, templates, VM disks), 4TB HDD (media library), 2TB SSD (staging for in-progress downloads).

## Build order (what `playbooks/site.yml` runs)

1. `proxmox/template.yml`   cloud-init VM template (API + SSH)
2. `cluster/create_vms.yml` clone template into kasrkin/wyvern/basilisk
3. `storage/nfs.yml`        NFS server on castellan, clients on VMs, mount/ownership/hardlink tests
4. `cluster/rke2.yml`       RKE2 servers then agents
5. `cluster/networking.yml` MetalLB and the ingress LoadBalancer address (see `docs/networking.md`)
6. `cluster/etcd_backup.yml` copy etcd snapshots to castellan (see `docs/runbooks/etcd-restore.md`)
7. `storage/kubernetes.yml` `media` namespace, NFS PVs/PVCs, local-path provisioner
8. `apps/jellyfin.yml`      Jellyfin
9. `apps/jellyfin_backup.yml` nightly backup CronJob

One-off, run by hand: `proxmox/bootstrap.yml`, `proxmox/harden.yml`, `proxmox/staging_disk.yml -e staging_disk_prepare=true`.
Day-2 tasks live in `playbooks/operations/`.

## Design rules

- **Playbooks are thin**: they say *where* (hosts) and *what* (roles). All logic is in `roles/`.
- **Inventory holds all site-specific values**; roles ship safe defaults only.
- **Data outlives the cluster**: all library data lives on castellan and is reached over NFS with `Retain` volumes.
  Deleting the cluster, a namespace or a claim never deletes a file.
- **Config does not live on NFS**: Jellyfin's SQLite database is on a node-local volume (local-path).
  The one exception is trickplay image files, which are mounted from the 2TB SSD so they survive a rebuild.
- **One export for `media/` and `downloads/`** so hardlinks work (a hardlink cannot cross mounts).
- **The library is mounted read-only into Jellyfin**: it can never modify or delete media.
- **Everything runs as one identity**: user/group `media` (1500). NFS squashes every client to it.
- **Safety switches**: disk formatting needs `-e staging_disk_prepare=true`; imports never delete; mounts are verified before any folder is created.

## Automation accounts (all created by the repo)

One name, `automation_user` (default `ansible`, set in `group_vars/all/main.yml`), is used everywhere:

| Where | Created by | Login |
|---|---|---|
| castellan, Linux user | `proxmox/bootstrap.yml` (first run as root with `-e ansible_user=root`; later runs as the user itself) | SSH key + passwordless sudo |
| castellan, Proxmox API user `<user>@pam`, role `Automation`, token `Automation` | `proxmox/bootstrap.yml` (tag `api`) | API token |
| the three VMs, Linux user | cloud-init, set by `roles/proxmox_vms` | SSH key + sudo |

The role's privileges are listed in `roles/proxmox_bootstrap/defaults/main.yml` (`proxmox_bootstrap_api_privileges`).
The token is created without privilege separation, so it has exactly the user's permissions.
Proxmox shows the token secret once, when the token is created. The playbook prints it at that moment; put it in the
vault as `vault_proxmox_api_token_secret`. Re-running never creates a second token. To replace it:
`ansible-playbook playbooks/proxmox/bootstrap.yml --tags api -e proxmox_bootstrap_rotate_token=true`, then update the vault.

## Repository layout

```
ansible.cfg  Makefile  requirements.{txt,yml}  .ansible-lint  .yamllint  .pre-commit-config.yaml
inventories/
  hosts.yml                     groups + addresses only
  group_vars/all/               main, versions, proxmox_api, media (libraries), template, vault (encrypted, untracked)
  group_vars/proxmox/           storage, import, template build settings
  group_vars/anvil_cluster/     VM sizing, kubernetes paths
  host_vars/<host>.yml          per-host overrides
playbooks/
  site.yml                      whole build
  proxmox/ cluster/ storage/ apps/    one playbook per stage
  operations/                   import, audit, flatten, diagnose
  common/storage_paths.yml      shared "where are the disks" play
roles/                          proxmox_*, storage_paths, nfs_server, nfs_client, rke2, k8s_storage, jellyfin, jellyfin_backup, media_import
docs/                           this folder
scripts/                        helper scripts (vault check, migration)
```

## Adding another environment

This repo has a single environment, so `inventories/` holds `hosts.yml`, `group_vars/` and `host_vars/` directly.
If you ever need a second one (for example a small test cluster), move these into `inventories/production/`, create
`inventories/test/` beside it, set `inventory = inventories/production/` in `ansible.cfg`, and select the other with `-i inventories/test`.
