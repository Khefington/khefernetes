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
5. `storage/kubernetes.yml` `media` namespace, NFS PVs/PVCs, local-path provisioner
6. `apps/jellyfin.yml`      Jellyfin
7. `apps/jellyfin_backup.yml` nightly backup CronJob

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

## Proxmox API token privileges

User `ansible@pam`, token `Automation`, role `Automation` with:
Datastore.Allocate Datastore.AllocateSpace Datastore.AllocateTemplate Datastore.Audit Pool.Allocate Sys.Audit Sys.Console Sys.Modify SDN.Use
VM.Allocate VM.Audit VM.Clone VM.Config.CDROM VM.Config.Cloudinit VM.Config.CPU VM.Config.Disk VM.Config.HWType VM.Config.Memory
VM.Config.Network VM.Config.Options VM.Migrate VM.PowerMgmt
The token secret is in the vault as `vault_proxmox_api_token_secret`.

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
