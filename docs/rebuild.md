# Rebuild runbook (destroy and recreate the cluster)

**Survives:** everything on castellan: the media library, Jellyfin backups, etcd snapshots, trickplay images, NFS exports, the VM template (9000).
**Rebuilt:** the three VMs, RKE2, MetalLB, the ingress, Kubernetes objects, Jellyfin.
**Restored from backup:** Jellyfin's database (users, watch history, library settings).
**Lost on purpose:** the old cluster's state. It was only ever built from this repo.

Take it one numbered step at a time and check the "You should see" line before going on. Nothing in steps 3 to 5 can touch your media.

## 1. Before you destroy anything
0. **Jellyfin version:** the repo now says Jellyfin 12. Upgrade the live server first (`docs/runbooks/jellyfin-upgrade.md`) and take a backup made by 12 (`make backup-now`); a rebuild then restores a 12 backup onto 12. Restoring a 10.11 zip onto a fresh 12 is untested (the restore warns).
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

## 2b. The short way: `make rebuild`
After step 2 you can run everything below (steps 3 to 6) with one command: `make rebuild`.
It checks first that the vault has every secret (a placeholder or a missing one stops it before anything is built), then runs, in this order:
`make site` (steps 3.1 to 3.8) > the Jellyfin restore (step 4; it stops and asks you to type `RESTORE`) > host firewall + updates > cluster hardening > WireGuard (and DuckDNS, if `ddns_duckdns_subdomain` is set) > one Jellyfin backup and one etcd snapshot > the read-only security audit > a short checklist of what to look at by hand (step 5).
- **First build, or nothing to restore:** `make rebuild ARGS="-e rebuild_restore=false"`.
- Other switches (all on by default; `-e name=false` turns one off): `rebuild_harden`, `rebuild_vpn`, `rebuild_backups`, `rebuild_audit`. Example: `make rebuild ARGS="-e rebuild_harden=false -e rebuild_audit=false"`.
- It is safe to run again if it stops half way: every stage looks first and only changes what differs. Fix the cause, run `make rebuild` again. If the failure was in the hardening part, the automatic rollbacks have already put things back.
- The first backups run **after** the restore, so the newest zip is the restored server, never an empty one. Do run it before the 05:30 job has fired on the new cluster.
- Still by hand: `make destroy-vms` (it deletes things, so it asks), the first-time Proxmox setup, and the router (the DNS server address, the UDP 51820 forward).
The stage-by-stage form in section 3 is for finding out which step breaks.

## 3. Rebuild, one stage at a time
| # | Command | You should see |
|---|---|---|
| 1 | `make vms` | three VMs created and booted (wyvern with the Intel iGPU attached, once the host is prepared with `make gpu-host`); then `make ping` answers `pong` from all of them |
| 1b | `make gpu-guest` | `GPU READY in the VM: /dev/dri/renderD128 exists`, HuC authenticated, `vainfo` lists the Intel iHD driver. (Skip steps 1b, 6b and 7b if no VM has `vm_gpu_passthrough`.) If the render device does not appear after a rebuild, the iGPU may not have reset cleanly when the old wyvern was destroyed: reboot castellan (the host setup is permanent) and run `make vms` and `make gpu-guest` again |
| 2 | `make nfs` | the NFS mount tests PASS on every VM, for all three exports |
| 3 | `make rke2` | the three nodes listed as Ready |
| 4 | `make etcd-backup` | the timer is installed (the first copy may say "no snapshots yet", which is fine) |
| 5 | `make networking` | `The ingress answers on http://192.168.1.200` |
| 6 | `make k8s-storage` | all 3 media claims `Bound`, then `Storage test passed on kasrkin, wyvern, basilisk` (a PASS/FAIL list per node is printed above it) |
| 6b | `make gpu-plugin` | each GPU node offers `gpu.intel.com/i915` (2 shares) |
| 7 | `make jellyfin` | pod ready, then the health check through the ingress answers |
| 7b | `make jellyfin-gpu-test` | every required check `OK`: H.264/HEVC encode and decode inside the Jellyfin pod on the GPU (the HDR probe is optional) |
| 8 | `make jellyfin-provision` | the first-run wizard done, plugins installed, the four libraries and the `Khef` user present, the backup key stored |

`make site` runs steps 1 to 8 in this order in one go (it stops at 7b if the GPU does not work, before Quick Sync is switched on). The stage-by-stage form above is for finding out which step breaks.

Castellan's DNS server (`make dns`) is not part of the rebuild: it runs on castellan and survives it. The router keeps pointing at it.

After step 3, on kasrkin, check the ingress is Traefik: `kubectl -n kube-system get pods | grep -i -E 'traefik|ingress-nginx'` should list a traefik pod on each node and no ingress-nginx.
After step 5: `kubectl get svc -A | grep LoadBalancer` should show `rke2-traefik` with EXTERNAL-IP `192.168.1.200`.

## 4. Jellyfin: set up, then restore the data
Step 3.8 already did everything this repo describes: the wizard, the `Khef` admin, the libraries, plugins, settings and the backup API key.
What is left is the data only a backup holds: watch history and each user's preferences.

**Checkpoint before restoring (this is the real test of the repo):** open `http://jellyfin.home.lan`, log in as `Khef` with the vault password, and look at Dashboard > Plugins (Open Subtitles Active; on a 10.11 rebuild also Intro Skipper and Bookshelf), Dashboard > Libraries (Movies, Shows, Music, Books) and Dashboard > API Keys (`khefernetes-backup`).
If all of that is there, the rebuild from the repo alone worked. Write down anything that was missing: that is a gap in the repo to fix.
0. Before restoring, look inside the backup you are about to use. Jellyfin's backup is a zip holding the database (users, watch history, saved home screen settings),
   the settings files (`system.xml`, `encoding.xml` with the hardware-acceleration setting, `branding.xml`), the profile pictures and the library definitions.
   A restore **replaces all of that with the zip's copy**, so anything you changed after the zip was taken is lost. From WSL, with a copy of the zip:
   `python3 scripts/inspect-jellyfin-backup.py ~/khefernetes-backups/<the zip>`
   It prints when the zip was taken, the hardware-acceleration value, whether profile pictures are inside, and how many watched / in-progress items and display settings the database holds.
   If a number is zero, or the time is before you made a change, pick a newer zip (run `make backup-now` on the old server before you destroy it).
1. `make jellyfin-restore`. It lists the zips Jellyfin can see (the HDD folder is mounted into the pod), picks the **newest**, checks it has a database and is not from a newer Jellyfin, and asks you to type `RESTORE`.
   To use an older one: `make jellyfin-restore ARGS="-e jellyfin_restore_archive=jellyfin-backup-<date>.zip"`. Jellyfin restarts and is unavailable for a minute or two.
   Do this **before the first nightly backup (05:30) runs on the new cluster**, otherwise the newest zip is a backup of the empty server (the list shows each zip's date, so you can spot it).
2. The same command then runs `make jellyfin-provision` for you (the restore brought back the old database, so this matches the libraries by folder, re-syncs the backup key and re-applies the settings from this repo; the password in the old database must match `vault_jellyfin_khef_password`),
   and re-attaches profile pictures (Jellyfin 10.11 restores the picture file but drops the database link that ties it to the user, [issue 15829](https://github.com/jellyfin/jellyfin/issues/15829)).
   Prefer the web UI? Dashboard > Backups > Restore works too; afterwards run `make jellyfin-provision` and `make jellyfin-profile-fix`.
3. `make backup-now`, then `make etcd-backup-now` (the new cluster has a new token, so take a fresh snapshot with it).
4. Dashboard > Scheduled Tasks: let "Extract Chapter Images" and "Generate Trickplay Images" run overnight; the trickplay, artwork and chapter images already on the SSD are adopted, not rebuilt.
5. `make diagnose-jellyfin` should show all PASS.
6. Check what the restore brought back for `Khef`: the home screen layout, "Continue Watching", watched marks, the profile picture (`make jellyfin-profile-check` reports it per user) and playback settings. Anything missing: run the inspector on the zip you restored and tell me what it shows.

If you do **not** need the old watch history, skip step 1 and 2: the provisioned server is already complete.

## 5. Verify against your baseline
- `make audit-media` is clean (the library never moved).
- Library item counts and users match what you wrote down.
- `kubectl get ingress -A` shows the Jellyfin ingress with ADDRESS `192.168.1.200`.
- A video plays, and scrubbing shows thumbnails (trickplay).
- If you want to practice a real etcd restore as well, do it now, before relying on the snapshots: `docs/runbooks/etcd-restore.md`.

## 6. Hardening after a rebuild
(`make rebuild` already does all of this; the list is for running the steps one at a time.)
The VMs are new, so their firewall and the cluster's policies are new too; castellan was not rebuilt, so its firewall and the VPN are still in place (the keys live on castellan).
1. `make host-firewall-apply` (VMs get their firewall; castellan's is unchanged and is skipped).
2. `make cluster-hardening-apply` (pod-security labels and the `media` NetworkPolicies, with live proofs).
3. `make security-audit`, and compare with the previous run.
4. `make wireguard` only if castellan itself was reinstalled (then re-issue every device with `make wireguard-client PEER=<name>`). Otherwise phones keep working: check one from outside the house.

## If something goes wrong
- **Any step 3 command fails:** read the message, fix, and re-run that same command. Every stage is safe to re-run.
- **Traefik misbehaves** (this is the first time that branch runs for real): set `ingress_controller: ingress-nginx` in `inventories/group_vars/anvil_cluster/kubernetes.yml`, then `make destroy-vms` and rebuild again. Switching a running cluster is a longer procedure, so a clean rebuild is quicker. Tell me what you saw and we will fix the Traefik branch.
- **You want to start over:** `make destroy-vms` and go back to step 3. Your media and backups are not involved.
- **The Jellyfin restore fails:** the backup zip is still on castellan and on your PC. Re-run the restore; nothing was changed in it.

## Why destroy-vms looks the way it does
`roles/proxmox_vms` has one switch, `proxmox_vms_state`: `present` (the default) builds a VM, `absent` stops and deletes it. The destroy playbook sets `absent`, refuses any VM that is not in `anvil_cluster`,
refuses the template's id, and checks that the VM it found in Proxmox has the expected name before it deletes anything.
