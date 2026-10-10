# Importing media from the Windows PC

```
make import-media        # copy (safe to re-run; never deletes)
make audit-media         # prove nothing is missing (read-only)
```

Configure sources in `inventories/group_vars/proxmox/import.yml`:
```yaml
media_transfers:
  - { src: "/mnt/c/Users/konno/Videos/Movies", library: movies }
```
`library` must be in `media_libraries`. Files land in `data/media/<library>/`. Trailing slashes do not matter.

## Reading the audit
```
== movies   ... -> .../media/movies/
   source:        1234 files, 800 GiB, 3 symlinks (1 broken) FOLLOWED
   destination:   1234 files, 800 GiB
   still to copy: 0 file(s)
   nested folder: no
```
- **still to copy > 0**: files missing or different. Run `make import-media`, then audit again.
- **nested folder: YES**: the folder was copied one level too deep (media/movies/Movies/...). Fix without copying anything:
  `make flatten-media` (report), then `make flatten-media APPLY=1`, then `make import-media` and `make audit-media`.
- **broken symlinks**: links that point nowhere have nothing to copy; they are skipped and counted.
- `-e media_import_checksum=true` also compares contents (reads every byte on both sides; slow but conclusive).

## Quick manual check on castellan
```
ls <hdd>/data/media/movies | head      # titles should be directly here, not inside one extra "Movies" folder
```
After an import, ask Jellyfin to rescan: `make import-media` with `-e import_refresh_jellyfin=true`, or press *Scan All Libraries*.
