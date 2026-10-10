# Migrating from the old layout

## One command
Commit everything in your old repo, unzip the new tree somewhere else, then from the OLD repo root:
```
bash /path/to/new-tree/scripts/migrate-from-cluster-layout.sh
```
Nothing is deleted. Old files go to `_old_layout/`, your encrypted vault moves to its new path, `.vault_pass` stays.

## What moved
| Old | New |
|---|---|
| `inventories/cluster/anvil.yml`, `castellan.yml` | `inventories/hosts.yml` |
| `inventories/cluster/group_vars/all/all.yml` | `group_vars/all/{main,versions,proxmox_api,media,template}.yml` |
| `inventories/cluster/group_vars/proxmox/vars.yml` | `group_vars/proxmox/{main,storage,import,template}.yml` |
| group vars inside `anvil.yml` | `group_vars/anvil_cluster/main.yml` |
| `playbooks/cluster/group_vars/all/all.yml` (`jellyfin_version`, `timezone`) | `group_vars/all/{versions,main}.yml` |
| `playbooks/proxmox/configure_proxmox.yml` | `playbooks/proxmox/bootstrap.yml` + role `proxmox_bootstrap` |
| `harden_proxmox.yml` | `playbooks/proxmox/harden.yml` + role `proxmox_hardening` |
| `prepare_staging_disk.yml` | `playbooks/proxmox/staging_disk.yml` + role `proxmox_staging_disk` |
| `vm_template_generation.yml` | `playbooks/proxmox/template.yml` + role `proxmox_vm_template` |
| `playbooks/cluster/create_vms.yml` | same path + role `proxmox_vms` |
| `install_rke2.yml` | `playbooks/cluster/rke2.yml` |
| `playbooks/storage/nfs_media.yml` | `playbooks/storage/nfs.yml` + roles `nfs_server`, `nfs_client` |
| `install_storage.yml` | `playbooks/storage/kubernetes.yml` + role `k8s_storage` |
| `install_jellyfin.yml`, `install_jellyfin_backup.yml` | `playbooks/apps/*.yml` + roles `jellyfin`, `jellyfin_backup` |
| `import_media.yml` | `playbooks/operations/import_media.yml` + role `media_import` |
| README dev log | `docs/devlog.md` |

## Renamed or removed variables
- `media_transfers[].dest: "media/books"` is now `library: books` (the old form is still accepted).
- `ansible_ssh_key_dir` (it is a file, not a directory) is now `admin_ssh_public_key_file`.
- `backup_schedule`, `backup_keep` are now `jellyfin_backup_schedule`, `jellyfin_backup_keep`.
- `transfer_excludes` is now `media_transfer_excludes`.
- Removed: `cluster_precedence` demos and the `anvil_precedence` group (the lesson is kept in `docs/ansible-precedence.md`),
  the stale `proxmox_prepare_vm_disk` / `vmdata` block, the unused `proxmox_host_*` variables (the token privileges are in
  `docs/architecture.md`), the duplicated `media_uid`/`media_gid`, `inventories/dev/dev.yml` (it was not a valid inventory),
  `kubernetes.core` and `lablabs.rke2` from `requirements.yml` (not used).

## Behaviour changes to know about
- Import now **follows symlinks** (they were silently skipped) and normalises trailing slashes (the old settings copied each folder one level too deep).
- `media/books` and `downloads/<library>` folders are created by `make nfs`.
- Trickplay is stored on the 2TB SSD (`/mnt/staging/appdata/jellyfin/trickplay`, mounted at `/config/data/trickplay`).
  Deploy in this order: `make nfs` (new export), `make k8s-storage` (new volume), `make jellyfin`. After that,
  turn OFF "Save trickplay images next to media" on each library, then run the *Generate Trickplay Images* task.
- Jellyfin gets a dedicated writable `/tmp` volume. Re-run `make jellyfin` (the pod restarts once).
- `create_vms.yml` previously relied on `template_name` and the Proxmox API settings being visible to the VMs;
  they now live in `group_vars/all`, where every play can see them.
- `vault.yml` is still git-ignored; see `docs/secrets.md`.

## After migrating
```
make syntax
make nfs            # creates media/books, downloads/<library>, the SSD appdata export
make k8s-storage    # adds the media-appdata volume
make jellyfin       # adds the /tmp and trickplay volumes
make audit-media    # check what is on the HDD
```
