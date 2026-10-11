# etcd snapshots: where they are and how to restore

etcd is the cluster's database (every Kubernetes object: namespaces, volumes, Deployments, MetalLB and ingress settings).
Your **media** and Jellyfin's **database** are not in it; they have their own backups. Losing etcd means rebuilding the cluster objects, which is why this exists.

## Where the snapshots are
| Place | What | How many |
|---|---|---|
| kasrkin, `/var/lib/rancher/rke2/server/db/snapshots/` | RKE2 takes one at 00:00 and 12:00 | newest 5 (RKE2 default) |
| castellan, `<hdd>/data/backups/etcd/kasrkin/` | a copy made by `khefernetes-etcd-copy` at 00:30 and 12:30 | newest 60 (`etcd_backup_keep`) |

The copy runs from a systemd timer on kasrkin, not from inside Kubernetes, so it still works when the cluster is unhealthy. The NFS share is mounted only while it runs.

## Set up and prove it works
```
make etcd-backup          # installs the script and timer, copies whatever exists
make etcd-backup-now      # takes a snapshot right now, copies it, and checks the copy has the same size
```
Look for `PASS: ... is on castellan`. Check on kasrkin with `systemctl list-timers khefernetes-etcd-copy.timer` and `journalctl -u khefernetes-etcd-copy`.

## The token matters
A snapshot is encrypted with a key derived from the RKE2 **server token** (`vault_rke2_token`). To restore a snapshot you need the token that was in use when it was taken.
- Snapshots taken before you switch to the new token can only be restored with the **old** token. After the rebuild with the new token, they are history; take a fresh one with `make etcd-backup-now`.
- Never rotate or discard a token while snapshots made with it are the ones you rely on.

## Restore: kasrkin is fine but the cluster state is broken
On kasrkin:
```
sudo systemctl stop rke2-server
sudo rke2 server --cluster-reset --cluster-reset-restore-path=/var/lib/rancher/rke2/server/db/snapshots/<snapshot file>
# wait until it says to restart without --cluster-reset, then:
sudo systemctl start rke2-server
```
If the newest local snapshot is bad or gone, copy one back from castellan first (see below). Then check `kubectl get nodes`; restart `rke2-agent` on the workers if they do not reconnect.

## Restore: the kasrkin VM is lost
1. `make vms` (recreates only VMs that are missing), then `make nfs`.
2. `make rke2` installs RKE2 on it with the token from the vault. For a restore, that token must be the one the snapshot was taken with.
3. Get a snapshot onto the new VM. From your PC: `ssh ansible@kasrkin`, then
   `sudo mount -t nfs -o nfsvers=4.2 192.168.1.50:<hdd>/data /mnt` and copy a file from `/mnt/backups/etcd/kasrkin/` to `/var/lib/rancher/rke2/server/db/snapshots/`; `sudo umount /mnt`.
4. Run the restore commands above. Because this is a fresh node, add `--token=<the token>` to the `rke2 server --cluster-reset ...` command if RKE2 asks for it.
5. Old node entries from before the loss may remain; delete any node that no longer exists with `kubectl delete node <name>`.

## Untested until you run it
These steps follow RKE2's documentation, but this repo has not yet performed a real restore. Do it once in the rebuild drill (`docs/rebuild.md`) before you need it.

## Changing the schedule or retention
RKE2's own schedule is controlled by `etcd-snapshot-schedule-cron` and `etcd-snapshot-retention` in `/etc/rancher/rke2/config.yaml`. They are left at their defaults here, so the copy times in `etcd_backup_calendar` assume 00:00 and 12:00.
If you change them, change `etcd_backup_calendar` to match.
