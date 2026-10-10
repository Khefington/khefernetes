# Trickplay (scrub-bar thumbnails) errors

Run the read-only diagnostic first:
```
make diagnose-jellyfin
```
It checks, as Jellyfin's own user (uid 1500): that every directory trickplay writes to is writable, that the library is read-only,
that ffmpeg can read a real file from each library and produce thumbnails, any unreadable files, the library trickplay settings,
whether the pod was OOM-killed, and the trickplay lines from Jellyfin's log.

## How Jellyfin 10.11 generates trickplay (from the source)
1. ffmpeg writes frames to `/tmp/jellyfin/<guid>/` (the container's temp dir).
2. Tiles are assembled in `/tmp/jellyfin/trickplay_<guid>/`.
3. The finished folder is moved to `/config/data/trickplay/<id>/`. In this repo that path is a mount of
   `/mnt/staging/appdata/jellyfin/trickplay` on the 2TB SSD, so the files outlive the cluster. (If "Save trickplay images next to media"
   is on, Jellyfin writes to `<media folder>/<file>.trickplay` instead, which fails on the read-only library.)
If a step fails it logs "Error creating trickplay images." with a stack trace; a tile that was never written shows up as a
file-not-found exception.

## Likely causes and fixes
| Finding | Cause | Fix |
|---|---|---|
| Library has "Save trickplay images next to media" ON | the library is mounted read-only on purpose, so the write fails | turn it off in Dashboard > Libraries > (library) |
| `/tmp` or `/config/data/trickplay` FAIL | permissions | the manifest now gives Jellyfin a dedicated writable `/tmp`; re-run `make jellyfin` |
| ffmpeg FAIL on a file | unreadable/corrupt file or codec issue | read the ffmpeg error shown; test the file in another player |
| pod `lastStopReason=OOMKilled` | ffmpeg plus scans exceeded the memory limit | raise `jellyfin_memory_limit` |
| `/media` unreadable files listed | ownership/mode wrong after an import | re-run `make import-media` (it re-applies owner and modes) |

**Keep "Save trickplay images next to media" OFF on every library.** The SSD-backed trickplay folder replaces what that setting
was for. After a rebuild, Jellyfin finds the existing tiles and imports them on its next scan instead of regenerating.

After fixing, run Dashboard > Scheduled Tasks > *Generate Trickplay Images*.
If it still fails, run the diagnostic and keep the "actual trickplay errors" section: the first stack frame names the exact step.
