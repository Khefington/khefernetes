# Jellyfin backup

First time:
1. `make jellyfin-provision` (it creates the API key the job needs and stores it as the Secret `jellyfin-api`).
2. `make jellyfin-backup` installs the CronJob (05:30 nightly, newest 14 kept).
3. `make backup-now` runs one immediately; the log should end with "Done."

Files land in `<hdd>/data/backups/jellyfin/`: a Jellyfin backup zip and a small settings archive.
Tune with `jellyfin_backup_schedule` and `jellyfin_backup_keep` (role defaults, or override in `group_vars/anvil_cluster/`).

## Restoring
Dashboard > Backups > Restore does the whole job: it replaces the database and overwrites the settings files (`Config/`: `system.xml`, `encoding.xml`, `branding.xml`, `users/<name>/profile.*`) and the library definitions (`Root/`) with the zip's copies. It does not delete files that are not in the zip.
Then run `make jellyfin-provision`: it renames the libraries to the names in the repo and re-applies plugin and server settings.
**Everything is "as of the moment the zip was taken".** Check the zip first: `python3 scripts/inspect-jellyfin-backup.py <the zip>` (read-only; shows the date, the hardware-acceleration setting, whether profile pictures are inside, and how many users / watched items / display settings it holds).
Plugin settings are not in the zip: `make jellyfin-provision` applies them from `jellyfin_plugin_settings`.

## How the pieces fit
- The backup folder on the HDD (`<hdd>/data/backups/jellyfin`) is mounted into the Jellyfin pod at `/config/data/backups`, which is where Jellyfin's own Dashboard > Backups page looks.
  So a backup made by the nightly job or by the Create button lands on the HDD directly, and every zip on the HDD shows up in the UI with a Restore button. Restoring after a rebuild needs no copying.
- Jellyfin's built-in backup holds the database (users, watch history, saved display settings) and the settings files (`Config/*.xml`, profile pictures, library definitions). The nightly job also saves `config/` and `root/` as `jellyfin-settings-<date>.tgz`, a second copy you can unpack by hand if a restore ever misses a file.
- The nightly job keeps the newest `jellyfin_backup_keep` of each kind. Backups made by hand in the UI are pruned by the same rule.
- Only this one folder is visible to Jellyfin. The media library stays read-only, and the etcd snapshots next to it are not exposed.
