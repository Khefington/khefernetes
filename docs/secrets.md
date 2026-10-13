# Secrets

Secrets are encrypted with ansible-vault in `inventories/group_vars/all/vault.yml`.
The vault password is in `.vault_pass` (git-ignored). Names are listed in `docs/examples/vault.example.yml`.

| Variable | Used for |
|---|---|
| `vault_ansible_become_password` | sudo on hosts that need it |
| `vault_proxmox_api_token_secret` | Proxmox API token secret |
| `vault_rke2_token` | RKE2 node join token |
| `vault_jellyfin_khef_password` | Password of the `Khef` Jellyfin admin (set when the account is created; also used to log in) |
| `vault_opensubtitles_username`, `vault_opensubtitles_password` | OpenSubtitles account used by the Jellyfin plugin |
| `vault_arr_password` | Password of the `khef` user on Sonarr, Radarr, Prowlarr and qBittorrent (`make arr-provision` sets it) |
| `vault_sonarr_api_key`, `vault_radarr_api_key`, `vault_prowlarr_api_key` | The apps' API keys, 32 hex characters each (`openssl rand -hex 16`); the apps read them from the environment, so a restored database cannot change them |
| `vault_nordvpn_wireguard_private_key` | NordLynx (WireGuard) private key for the downloader's tunnel; how to get it: `docs/runbooks/download-stack.md` |
| `vault_duckdns_token` | DuckDNS token for the dynamic-DNS updater (`make ddns`); stored on castellan in a root-only file |

The Jellyfin API key (backups, rescans) is no longer a vault secret: `make jellyfin-provision` creates it and stores it in the cluster as the Secret `jellyfin-api`.

Commands:
```
ansible-vault create inventories/group_vars/all/vault.yml
ansible-vault edit   inventories/group_vars/all/vault.yml
ansible-vault rekey  inventories/group_vars/all/vault.yml   # change the vault password
```

## Rules
- Never paste a secret into chat, an issue, a playbook, a template, or a file that is not encrypted.
- Never share `.vault_pass` or an unfiltered zip of the repo. Exclude `.vault_pass`, `vault.yml` and `.venv`.
- Rotate anything that has left your machine: change it at the source (Proxmox token, Jellyfin API key, passwords), then update the vault.
- The pre-commit hook `vault-must-be-encrypted` refuses a plaintext vault.

## Tracked or untracked?
`vault.yml` is git-ignored here. The common industry alternative is to commit the *encrypted* file (a strong vault password
and a password manager copy of `.vault_pass` make that safe) so a rebuild needs only the repo and one password.
To switch, delete the `vault.yml` line from `.gitignore`. If it was ever committed before, history still has the old version;
rotate those secrets.
