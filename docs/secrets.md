# Secrets

Secrets are encrypted with ansible-vault in `inventories/group_vars/all/vault.yml`.
The vault password is in `.vault_pass` (git-ignored). Names are listed in `docs/examples/vault.example.yml`.

| Variable | Used for |
|---|---|
| `vault_ansible_become_password` | sudo on hosts that need it |
| `vault_proxmox_api_token_secret` | Proxmox API token secret |
| `vault_rke2_token` | RKE2 node join token |
| `vault_jellyfin_api_key` | Jellyfin backup job and rescans |

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
