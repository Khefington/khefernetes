# Rebuild runbook (destroy and recreate the cluster)

What survives: everything on castellan (library, backups, NFS exports, Proxmox template).
What is rebuilt: the three VMs, RKE2, Kubernetes objects, Jellyfin.
What is restored: Jellyfin's database (users, watch history, libraries) from the nightly backup.

## 1. Before you destroy anything
1. `make backup-now` and confirm the log ends with "Done." A file must exist in `<hdd>/data/backups/jellyfin/`.
   Also `make etcd-backup-now` and look for `PASS`: the cluster snapshot is then in `<hdd>/data/backups/etcd/kasrkin/` (restore steps: `docs/runbooks/etcd-restore.md`).
2. Copy that backup off castellan too (a restore drill is only real if the backup is outside the thing you destroy).
3. Confirm you have `.vault_pass` and the vault file.

## 2. Destroy
Stop and delete VMs 201-203 in Proxmox (or `qm destroy`). Do not touch the HDD, the staging SSD or template 9000.

## 3. Rebuild
```
make vms nfs rke2 etcd-backup networking k8s-storage jellyfin
```
(`make site` does the same plus the template and the backup job.)

## 4. Restore Jellyfin
1. Open Jellyfin and complete the first-run wizard (any user).
2. Dashboard > Backups > upload/select the newest backup zip from `<hdd>/data/backups/jellyfin/` and restore. Jellyfin restarts.
3. Create a new API key (Dashboard > Advanced > API Keys), put it in the vault as `vault_jellyfin_api_key`, then `make jellyfin-backup`.
4. `make diagnose-jellyfin` should show all PASS.

## 5. Verify
- `make audit-media` is clean (the library never moved).
- Libraries and watch history are back. Trickplay files are still on the SSD; Jellyfin adopts them on its next library scan
  (Dashboard > Scan All Libraries) instead of regenerating them.
