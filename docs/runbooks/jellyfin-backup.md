# Jellyfin backup

First time:
1. `make jellyfin-provision` (it creates the API key the job needs and stores it as the Secret `jellyfin-api`).
2. `make jellyfin-backup` installs the CronJob (05:30 nightly, newest 14 kept).
3. `make backup-now` runs one immediately; the log should end with "Done."

Files land in `<hdd>/data/backups/jellyfin/`: a database backup zip and a small settings archive.
Tune with `jellyfin_backup_schedule` and `jellyfin_backup_keep` (role defaults, or override in `group_vars/anvil_cluster/`).

## How the pieces fit
- The backup folder on the HDD (`<hdd>/data/backups/jellyfin`) is mounted into the Jellyfin pod at `/config/data/backups`, which is where Jellyfin's own Dashboard > Backups page looks.
  So a backup made by the nightly job or by the Create button lands on the HDD directly, and every zip on the HDD shows up in the UI with a Restore button. Restoring after a rebuild needs no copying.
- Jellyfin's built-in backup holds the database (users, watch history, libraries). It does not hold the settings files (`system.xml`, `network.xml`, `encoding.xml` and friends). The nightly job saves those separately as `jellyfin-settings-<date>.tgz`.
- The nightly job keeps the newest `jellyfin_backup_keep` of each kind. Backups made by hand in the UI are pruned by the same rule.
- Only this one folder is visible to Jellyfin. The media library stays read-only, and the etcd snapshots next to it are not exposed.
