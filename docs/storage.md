# Storage

## Layout on the HDD (`<hdd>/data`, exported over NFS)

```
data/
  media/<library>/        what Jellyfin (read-only) and other apps read      movies tv music books
  downloads/<library>/    finished downloads per category; hardlinked into media/
  backups/jellyfin/       nightly Jellyfin backups
/mnt/staging/incomplete   (2TB SSD, separate export) in-progress downloads
/mnt/staging/appdata      (2TB SSD, separate export) app files; jellyfin/trickplay is mounted at /config/data/trickplay
```

`media_libraries` in `inventories/group_vars/all/media.yml` is the single source of truth.
Add a name there and run `make nfs`; folders for both `media/` and `downloads/` are created.

## Hardlinks (why `media/` and `downloads/` share an export)

A hardlink is a second name for the same data on the same filesystem. When a completed download is hardlinked into
`media/`, seeding continues from `downloads/` and the file is stored once. Hardlinks cannot cross mounts, so both
folders must be inside one export and one mount. `playbooks/storage/nfs.yml` proves this works on every VM.

### Importing files that were hardlinked on Windows
rsync reads every name as a separate file and copies the data for each, so **nothing is missing**; hardlinked
duplicates simply use extra space on the HDD. Recreating the links is available (`media_import_preserve_hardlinks: true`)
but off by default, because inode numbers over WSL's Windows-drive mount are not guaranteed unique, and a false
match would link two different files.
What *can* silently go missing: **symlinks and junctions** (skipped by older versions of the import, now followed),
and anything copied one folder too deep (missing trailing slash). `make audit-media` finds both.

## Books

Jellyfin has no first-class "books" library type, so books are stored in `media/books` for apps built for them
(Kavita, Calibre-Web, Audiobookshelf for audiobooks). They mount the same `media-data` claim with `subPath: media/books`.
Jellyfin itself mounts only `media/` read-only and ignores the folder unless you add a library for it.

## Running a large library

- **Prove, do not assume**: run `make audit-media` after every import (counts, sizes, per-file dry run, optional checksum).
- **Never import with `--delete`**: the tooling has no delete mode.
- **Filesystem**: ext4 on the HDD is fine. For multi-disk growth or checksummed integrity consider ZFS/btrfs later;
  the layout above does not change.
- **Backups (3-2-1)**: the library itself is not backed up yet (one copy on one disk). Plan a second copy
  (external drive or another host) before treating the data as safe. Jellyfin's database is backed up nightly to the same HDD,
  which protects against Jellyfin mistakes, not disk failure.
- **Monitoring**: watch free space on the HDD (`df -h`) and SMART health (`smartctl` is installed on castellan).
- **Library scans**: Jellyfin cannot see changes made over NFS by another machine. After an import run
  `-e import_refresh_jellyfin=true` or press *Scan All Libraries*.
- **Metadata stays off the library**: with the library read-only, Jellyfin keeps its database and metadata in `/config`
  (node-local, 20Gi by default; raise `jellyfin_config_size` for a very large library).
- **Trickplay lives on the 2TB SSD** (`/mnt/staging/appdata/jellyfin/trickplay`), not in `/config`, so it is fast to browse and
  survives a rebuild: a new Jellyfin finds the existing files and adopts them instead of regenerating. It is the one part of
  `/config` that is on NFS; the SQLite database must never be. Keep at least 20% of the SSD free.
