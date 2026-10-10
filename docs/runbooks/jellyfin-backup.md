# Jellyfin backup

First time:
1. Jellyfin > Dashboard > Advanced > API Keys > "+" > name it `backup` > copy the key.
2. `ansible-vault edit inventories/group_vars/all/vault.yml` and add `vault_jellyfin_api_key: <key>`.
3. `make jellyfin-backup` installs the CronJob (03:15 nightly, newest 14 kept).
4. `make backup-now` runs one immediately; the log should end with "Done."

Files land in `<hdd>/data/backups/jellyfin/`: a database backup zip and a small settings archive.
Tune with `jellyfin_backup_schedule` and `jellyfin_backup_keep` (role defaults, or override in `group_vars/anvil_cluster/`).
