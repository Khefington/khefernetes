# Rebuild runbook (destroy and recreate the cluster)

**Survives:** everything on castellan: the media library, Jellyfin backups, etcd snapshots, trickplay images, NFS exports, the VM template (9000).
**Rebuilt:** the three VMs, RKE2, MetalLB, the ingress, Kubernetes objects, Jellyfin.
**Restored from backup:** Jellyfin's database (users, watch history, library settings).
**Lost on purpose:** the old cluster's state. It was only ever built from this repo.

Take it one numbered step at a time and check the "You should see" line before going on. Nothing in steps 3 to 5 can touch your media.

## 1. Before you destroy anything
1. Apply the repo to your checkout, then `git status` and commit. From now until the VMs are gone, **do not run `make rke2`, `make networking` or `make jellyfin` against the live cluster**: the inventory now says Traefik and the new RKE2 token.
2. Make sure your Python tools are current: `make setup`, then `source .venv/bin/activate`. The Proxmox steps (`make vms`, `make destroy-vms`) need proxmoxer 2.3 or newer, and they stop with a message if it is older.
3. Open the vault (`ansible-vault edit inventories/group_vars/all/vault.yml`) and confirm `vault_rke2_token` is the new token you generated.
4. `make backup-now`. *You should see:* the log ends with "Done.", and a new zip exists in `<hdd>/data/backups/jellyfin/`.
5. `make etcd-backup-now`. *You should see:* `PASS: ... is on castellan`.
6. Copy the newest Jellyfin backup off castellan, for example from WSL:
   `scp ansible@castellan:/mnt/pve/castellan-hdd1/data/backups/jellyfin/<newest file> ~/khefernetes-backups/`
   A restore drill only counts if the backup lives outside the thing you destroy.
7. Write down a baseline to compare against later: how many items each Jellyfin library shows, your users, and one thing with watch history.
   On kasrkin: `kubectl get nodes -o wide` and `kubectl get ingress -A`.

## 2. Destroy
`make destroy-vms` and type `DESTROY` when asked.
*You should see:* VMs 201, 202 and 203 gone in the Proxmox web UI, template 9000 still there, and the HDD and SSD untouched.
The playbook removes the old SSH host keys from your PC too, so the new VMs will not trigger "host key changed" errors.

## 3. Rebuild, one stage at a time
| # | Command | You should see |
|---|---|---|
| 1 | `make vms` | three VMs created and booted; then `make ping` answers `pong` from all of them |
| 2 | `make nfs` | the NFS mount tests PASS on every VM, for all three exports |
| 3 | `make rke2` | the three nodes listed as Ready |
| 4 | `make etcd-backup` | the timer is installed (the first copy may say "no snapshots yet", which is fine) |
| 5 | `make networking` | `The ingress answers on http://192.168.1.200` |
| 6 | `make k8s-storage` | all 3 media claims `Bound` |
| 7 | `make jellyfin` | pod ready, then the health check through the ingress answers |
| 8 | `make jellyfin-provision` | the first-run wizard done, plugins installed, the four libraries and the `Khef` user present, the backup key stored |

Castellan's DNS server (`make dns`) is not part of the rebuild: it runs on castellan and survives it. The router keeps pointing at it.

After step 3, on kasrkin, check the ingress is Traefik: `kubectl -n kube-system get pods | grep -i -E 'traefik|ingress-nginx'` should list a traefik pod on each node and no ingress-nginx.
After step 5: `kubectl get svc -A | grep LoadBalancer` should show `rke2-traefik` with EXTERNAL-IP `192.168.1.200`.

## 4. Jellyfin: set up, then restore the data
Step 3.8 already did everything that comes from Git: the wizard, the `Khef` admin, the libraries, plugins, settings and the backup API key.
What is left is the data only a backup holds: watch history and each user's preferences.
1. Dashboard > Backups: the nightly zips from the HDD are already listed (that folder on castellan is mounted into the Jellyfin pod). Pick the newest and click Restore. Jellyfin restarts and is unavailable for a minute or two.
2. Run `make jellyfin-provision` again. The restore brought back the old database, so this re-syncs the backup key and re-applies the settings from Git. Log in with the password that was in the old database; it must match `vault_jellyfin_khef_password`.
3. `make backup-now`, then `make etcd-backup-now` (the new cluster has a new token, so take a fresh snapshot with it).
4. Dashboard > Scheduled Tasks: let "Extract Chapter Images" and "Generate Trickplay Images" run overnight; the trickplay, artwork and chapter images already on the SSD are adopted, not rebuilt.
5. `make diagnose-jellyfin` should show all PASS.

If you do **not** need the old watch history, skip step 1 and 2: the provisioned server is already complete.

## 5. Verify against your baseline
- `make audit-media` is clean (the library never moved).
- Library item counts and users match what you wrote down.
- `kubectl get ingress -A` shows the Jellyfin ingress with ADDRESS `192.168.1.200`.
- A video plays, and scrubbing shows thumbnails (trickplay).
- If you want to practice a real etcd restore as well, do it now, before relying on the snapshots: `docs/runbooks/etcd-restore.md`.

## If something goes wrong
- **Any step 3 command fails:** read the message, fix, and re-run that same command. Every stage is safe to re-run.
- **Traefik misbehaves** (this is the first time that branch runs for real): set `ingress_controller: ingress-nginx` in `inventories/group_vars/anvil_cluster/kubernetes.yml`, then `make destroy-vms` and rebuild again. Switching a running cluster is a longer procedure, so a clean rebuild is quicker. Tell me what you saw and we will fix the Traefik branch.
- **You want to start over:** `make destroy-vms` and go back to step 3. Your media and backups are not involved.
- **The Jellyfin restore fails:** the backup zip is still on castellan and on your PC. Re-run the restore; nothing was changed in it.

## Why destroy-vms looks the way it does
`roles/proxmox_vms` has one switch, `proxmox_vms_state`: `present` (the default) builds a VM, `absent` stops and deletes it. The destroy playbook sets `absent`, refuses any VM that is not in `anvil_cluster`,
refuses the template's id, and checks that the VM it found in Proxmox has the expected name before it deletes anything.
