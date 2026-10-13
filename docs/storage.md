# Storage

## Layout on the HDD (`<hdd>/data`, exported over NFS)

```
data/
  media/<library>/        what Jellyfin (read-only) and other apps read      movies tv music books
  downloads/<library>/    finished downloads per category; hardlinked into media/
  backups/jellyfin/       nightly Jellyfin backups
  backups/arr/            nightly Sonarr / Radarr / Prowlarr backups (14 kept each)
/mnt/staging/incomplete   (2TB SSD, separate export) in-progress downloads
/mnt/staging/appdata      (2TB SSD, separate export) app files that are expensive to regenerate:
                            jellyfin/trickplay, jellyfin/metadata, jellyfin/subtitles, jellyfin/attachments
                            (the list is `jellyfin_persisted_dirs`; each is mounted into the Jellyfin pod)
```

`media_libraries` in `inventories/group_vars/all/media.yml` is the single source of truth.

Who mounts what (download stack, `docs/runbooks/download-stack.md`): qBittorrent sees only `downloads/` (at `/data/downloads`) and the SSD `incomplete` folder, never the library; Sonarr and Radarr see the whole data share at `/data`, so `/data/downloads/tv/...` and `/data/media/tv/...` are one filesystem and an import is a hardlink. The same absolute paths are used in every container, so no remote-path mapping is needed. Their databases live on node-local volumes (SQLite), backed up nightly to `backups/arr/`.
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

## Proving the storage works (`make k8s-storage`)
After the volumes exist, `make k8s-storage` starts one short-lived pod on every node, with the same user and limits as the real apps, and prints a PASS/FAIL list per node:
- the three shared volumes are NFS, can be written and read, and files come out owned by the media user (1500:1500)
- a file can be hardlinked from `downloads/` into `media/` (one filesystem, so the download apps can use hardlinks)
- the library as Jellyfin sees it (`media/`, read-only) refuses writes and contains every folder in `media_libraries`
- the node-local volume is a real local disk and supports file locking (what Jellyfin's SQLite database needs)

The pods and their test volumes are deleted afterwards, pass or fail. It takes about a minute (the first run pulls a small image, `storage_test_image`).
If a check fails the playbook stops and the FAIL lines say which. Skip it with `make k8s-storage ARGS="-e k8s_storage_run_test=false"`.

## What stays on the node, and why
Jellyfin's SQLite database (`/config/data/jellyfin.db`) stays on the node-local volume, because SQLite needs a real local disk
(file locking over NFS is unreliable). It is protected by the nightly backup instead. Everything that is only files and costly to
recreate (thumbnails, artwork, chapter images, extracted subtitles) is on the SSD and survives a rebuild.

The database remembers where each image is. If it is restored on a node whose metadata folder is empty, Jellyfin logs
`Could not find file '/config/metadata/...'` for every missing image until it is refreshed. Keeping the metadata folder on the SSD avoids this.
