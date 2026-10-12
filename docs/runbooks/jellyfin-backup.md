# Jellyfin backup

First time:
1. `make jellyfin-provision` (it creates the API key the job needs and stores it as the Secret `jellyfin-api`).
2. `make jellyfin-backup` installs the CronJob (05:30 nightly, newest 14 kept).
3. `make backup-now` runs one immediately; the log should end with "Done."

Files land in `<hdd>/data/backups/jellyfin/`: a Jellyfin backup zip and a small settings archive.
Tune with `jellyfin_backup_schedule` and `jellyfin_backup_keep` (role defaults, or override in `group_vars/anvil_cluster/`).

## Restoring
`make jellyfin-restore` is the normal way (the same as Dashboard > Backups > Restore, with checks and clean-up):
1. It asks Jellyfin which zips it can see, shows them newest first and picks the newest. `-e jellyfin_restore_archive=<file name>` picks another.
2. It refuses a zip with no database or from a newer Jellyfin than the running one, then asks you to type `RESTORE`.
3. It starts the restore and waits for Jellyfin to come back.
4. It runs `make jellyfin-provision` (renames libraries to the repo's names, re-applies plugin and server settings, refreshes the backup key). Skip with `-e jellyfin_restore_provision=false`.
5. It re-attaches profile pictures (see below).
A restore replaces the database and overwrites the settings files (`Config/`: `system.xml`, `encoding.xml`, `branding.xml`, `users/<name>/profile.*`) and the library definitions (`Root/`) with the zip's copies. It does not delete files that are not in the zip.
**Everything is "as of the moment the zip was taken".** Check a zip first: `python3 scripts/inspect-jellyfin-backup.py <the zip>` (read-only; shows the date, the hardware-acceleration setting, whether profile pictures are inside, and how many users / watched items / display settings it holds).
Plugin settings are not in the zip: `make jellyfin-provision` applies them from `jellyfin_plugin_settings`.
Run the restore soon after a rebuild: the nightly job (05:30) would otherwise write a backup of the empty server, and that becomes the "newest".

### Profile pictures
Jellyfin 10.11 has a restore bug ([issue 15829](https://github.com/jellyfin/jellyfin/issues/15829)): the picture file is put back (`/config/config/users/<name>/profile.png`) but the database row that links it to its user loses the user, so the avatar is blank.
- `make jellyfin-profile-check` (read-only): for every user, is the picture linked? lists picture files found in the pod.
- `make jellyfin-profile-fix`: uploads the file on disk again through Jellyfin's API for every user whose picture is not linked. This is the last step of `make jellyfin-restore`.
If the stored API key is rejected (after a restore without provisioning), run `make jellyfin-provision` first.

## How the pieces fit
- The backup folder on the HDD (`<hdd>/data/backups/jellyfin`) is mounted into the Jellyfin pod at `/config/data/backups`, which is where Jellyfin's own Dashboard > Backups page looks.
  So a backup made by the nightly job or by the Create button lands on the HDD directly, and every zip on the HDD shows up in the UI with a Restore button. Restoring after a rebuild needs no copying.
- Jellyfin's built-in backup holds the database (users, watch history, saved display settings) and the settings files (`Config/*.xml`, profile pictures, library definitions). The nightly job also saves `config/` and `root/` as `jellyfin-settings-<date>.tgz`, a second copy you can unpack by hand if a restore ever misses a file.
- The nightly job keeps the newest `jellyfin_backup_keep` of each kind. Backups made by hand in the UI are pruned by the same rule.
- Only this one folder is visible to Jellyfin. The media library stays read-only, and the etcd snapshots next to it are not exposed.
