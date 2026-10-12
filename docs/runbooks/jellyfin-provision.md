# Jellyfin as code (`make jellyfin-provision`)

What it does, in the order a person would click through it. Every step looks first and changes only what differs, so it is safe to repeat.

1. Waits until Jellyfin answers (through the ingress, like a browser).
2. Completes the first-run wizard if it was never completed (server name, language, the admin account, remote access).
3. Logs in as the admin.
4. Registers plugin repositories and installs the plugins you list, then restarts Jellyfin once if anything was installed.
5. Merges `jellyfin_server_config` into the server settings (scan concurrency, trickplay threads, ...).
6. Merges `jellyfin_plugin_settings` into each plugin's saved settings.
7. Creates or updates the libraries. A library is matched by its folder, so a restored library with another name is adopted and renamed, not duplicated.
8. Creates users and sets who is admin and which libraries each can see. A password is only set when the account is created.
9. Creates the API key the backup job uses and stores it in the cluster as the Secret `jellyfin-api`.

Everything it applies is in `inventories/group_vars/all/jellyfin.yml`; the passwords come from the vault.

## Common changes
- **Add a user:** add an entry to `jellyfin_users` (with a `vault_...` password), then `make jellyfin-provision`.
- **Add a library:** add an entry to `jellyfin_libraries`; the folder must exist (add it to `media_libraries` and run `make nfs`).
- **Add a plugin:** add its repository (if third-party) and its catalogue name, then run it. The end of the run prints the installed versions: copy them into the list as `version:` to pin them.
- **Plugin settings (OpenSubtitles login, ...):** run `make jellyfin-provision ARGS="-e jellyfin_provision_show_plugin_config=true"` to list each plugin's setting names (secrets are shown as `***`), then put the values under `jellyfin_plugin_settings`.

## If it stops
- *Could not log in as Khef*: the server was restored from a backup and the old password applies. Put it in the vault as `vault_jellyfin_khef_password`.
- *'<name>' is not offered by any registered repository*: the message lists the names on offer; fix the spelling or add the repository.
- *Jellyfin did not answer*: check `kubectl -n media get pods` and `kubectl get ingress -A`.

## Notes
- Third-party plugins run inside Jellyfin with full access to what it can reach. Add only plugins you have looked at, and pin their versions.
- Before raising `jellyfin_version`, check that every plugin in the list supports the new version.
- Library options keep "save next to media" off because the library is mounted read-only; thumbnails and chapter images are built by the nightly tasks (02:00 and 03:00), not during a scan.
