# Upgrading Jellyfin from 10.11 to 12

Jellyfin 12 is a one-way trip: on its first start it rewrites its database, and an older Jellyfin cannot read the result. So this repo
never does it as a side effect. `make jellyfin` and `make site` **refuse** to change the major version of a running Jellyfin;
the upgrade is its own command with a check first, a backup, a copy of the config volume and a rollback.

## What changes in 12 (and what this repo does about it)
| Change | Effect here |
|---|---|
| Database migration on first start (minutes, longer for a big library) | Jellyfin is off while it runs. The pod is given up to 45 minutes (`jellyfin_upgrade_startup_minutes`) before Kubernetes may restart it. Never interrupt it. |
| Usernames are case-insensitive; two accounts that differ only in capitals fail the migration | `make jellyfin-upgrade-check` lists them as a BLOCKER. |
| Plugins move to .NET 10; every 10.11 plugin stops loading | The upgrade uninstalls all of them first; `make jellyfin-provision` installs the ones that have a 12 build. |
| Intro Skipper (third party) has no 12 build | Removed from `jellyfin_plugins`. You lose the "Skip intro" button until it ships one. |
| Bookshelf (books metadata) is built in | Removed from `jellyfin_plugins`. |
| Open Subtitles | Un-pinned (`{name: Open Subtitles}`): the catalogue picks the build that targets 12. Pin the version printed at the end once it works. |
| Old-style authentication (`X-Emby-*` headers, `?api_key=`) is off by default and the `/emby` routes are gone | Already off since hardening stage 3. A very old client that stops signing in must be updated. |
| FFmpeg 8.1 | `make jellyfin-gpu-test` runs at the end of the upgrade. |
| Only 10.10.7 and 10.11.x can upgrade | The check refuses anything older. |

The repo pins the immutable image tag `12.2.20261005-225228` (`inventories/group_vars/all/versions.yml`). The plain `12.2` tag moves with patch releases.

## The order I recommend
1. **Upgrade the running server first**, then take a backup made by 12, **then** do any teardown/rebuild. A rebuild drill restores a backup; restoring a
   10.11 zip onto a fresh 12 is not something this repo has tested (the restore prints a warning), while restoring a 12 backup onto 12 is the normal path.
2. If you rebuild before upgrading: put `jellyfin_version: "10.11.11"` and the old plugin list back for that rebuild, and upgrade afterwards.

## 1. Check (read-only)
```
make jellyfin-upgrade-check
```
*You should see:* the running version, the image tag the repo asks for, users, the plugins that will be uninstalled, the backups Jellyfin can see, the room on the config volume,
and `Ready. Run: make jellyfin-upgrade`. Anything marked **BLOCKER** must be fixed first (rename or delete the duplicate-case user in Dashboard > Users, free disk space, ...).
**WARNING** lines are things to know: someone is playing a film, a scheduled task is running.

## 2. Upgrade
```
make jellyfin-upgrade
```
It asks you to type `UPGRADE`, then:
1. Pulls the new image onto the node (a wrong tag fails now, while Jellyfin is still on).
2. Takes a backup through the nightly job and checks Jellyfin lists it (database included, made after you typed `UPGRADE`).
3. Uninstalls the plugins, **stops Jellyfin, copies the config volume** on the node to `<volume>-pre-upgrade-<version>-<time>` (the fast way back), starts 12 and waits for the migration.
4. Moves the nightly backup job to the new image and re-applies the settings from Git (`make jellyfin-provision`: installs the plugins that have a 12 build, re-applies server settings, users, libraries).
5. Starts a library scan, takes a second backup (now made by 12), and last runs `make jellyfin-gpu-test`.
   Steps 4 to 6 are also available alone as `make jellyfin-upgrade-finish`.

*You should see:* "Jellyfin 12.2... is running" and the path of the volume copy. Plan for 10 to 30 minutes of Jellyfin being unavailable on a normal library.
Watch the migration with `kubectl -n media logs deploy/jellyfin -f` (on kasrkin). If the GPU test fails, everything else has already happened; see "GPU" below.

## 3. After the upgrade (look at it before you delete anything)
- Sign in as Khef; the four libraries are there and the item counts match what you wrote down.
- Watch history, "continue watching" and each user's preferences survived (open a user that has history).
- Dashboard > Plugins: Open Subtitles Active. Dashboard > API Keys: `khefernetes-backup`.
- Play something that needs transcoding; `make jellyfin-transcode-check` shows whether the GPU did the work.
- A phone/TV client that cannot sign in is the legacy-auth change: update the app.
- Dashboard > Scheduled Tasks: the library scan finishes; thumbnails are rebuilt by the usual 02:00 / 03:00 tasks.
- A few days later, when you are happy: `make jellyfin-upgrade-cleanup` (asks for `DELETE`) removes the volume copies from the node.
  Pin the Open Subtitles version in `jellyfin.yml`.

## 4. If it goes wrong
**Fast way back (needs the volume copy, i.e. do it before cleaning up):**
```
make jellyfin-rollback JELLYFIN_OLD=10.11.11
```
Type `ROLLBACK`. It stops Jellyfin, keeps the 12 volume beside it as `-failed-<time>`, puts the copy back and starts 10.11.11. Anything done after the upgrade is lost.
Then set `jellyfin_version` back to `"10.11.11"` in `versions.yml` and put the old plugin lines back in `jellyfin.yml` so the repo matches (otherwise `make jellyfin` refuses, on purpose).

**Slow way back (no volume copy; uses the backup zip taken before the upgrade; written from Jellyfin's documentation, not tested here):**
1. On kasrkin: `kubectl -n media scale deployment/jellyfin --replicas=0`. On the node, move the config volume folder aside (`mv <folder> <folder>-12`) and make a new empty one with the same owner.
2. In the repo: `jellyfin_version: "10.11.11"`, then `make jellyfin ARGS="-e jellyfin_allow_downgrade=true"` and `make jellyfin-provision` (a clean 10.11 with the wizard done).
3. `make jellyfin-restore ARGS="-e jellyfin_restore_archive=<the zip the upgrade printed>"`.

**`make jellyfin-upgrade` stopped with "did not come up cleanly" but the log shows Jellyfin working:** this is normal on a big library. The pod counts as ready while the server still
says `Degraded` ("Server is still starting up"); the database migration and clean-up passes run in that time. Do **not** roll back. Wait until `kubectl -n media logs deploy/jellyfin --tail=20`
stops showing migration lines and `/health` says `Healthy`, then run `make jellyfin-upgrade-finish`: it waits for Healthy, then does steps 4 to 6 (settings from Git, scan, second backup, GPU test). It is safe to repeat.

**The migration seems stuck:** do not delete the pod. A large library can take a long time; `kubectl -n media logs deploy/jellyfin -f` shows progress. The pod's start-up allowance is `jellyfin_upgrade_startup_minutes` (45).

**GPU test fails after the upgrade:** FFmpeg 8 changed. `make jellyfin-gpu-test` says which check failed; the usual workaround is `EnableTonemapping: false` in `jellyfin_encoding_config` then `make jellyfin-provision`. Playback still works in software meanwhile.

## Knobs (all optional; defaults in `roles/jellyfin/defaults/main.yml`)
| Variable | Default | Meaning |
|---|---|---|
| `jellyfin_upgrade_confirm` | "" | `-e jellyfin_upgrade_confirm=UPGRADE` skips the question |
| `jellyfin_upgrade_snapshot` | true | copy the config volume first; `false` relies on the backup zip alone |
| `jellyfin_upgrade_startup_minutes` | 45 | how long Kubernetes waits for Jellyfin to answer after the new start |
| `jellyfin_upgrade_space_factor` | 3 | the check wants this many times the config volume's size free |
| `jellyfin_upgrade_pull_image` | true | pre-pull the image on the node |
| `jellyfin_rollback_confirm` / `jellyfin_cleanup_confirm` | "" | skip the `ROLLBACK` / `DELETE` question |
