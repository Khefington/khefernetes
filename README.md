# khefernetes
Ansible-driven RKE2 cluster on Proxmox to host media server.

# Dependencies
[Python]
ansible-core>=2.16
ansible-lint
proxmoxer
requests

[Ansible]
  - name: community.proxmox
  - name: community.general
  - name: ansible.posix
  - name: kubernetes.core

## Repository Layout

| Path | Purpose |
|---|---|
| `inventories/cluster/hosts.yml` | Proxmox host and the planned VMs |
| `group_vars/` | Network, storage and version settings |
| `roles/proxmox_host/` | Repos, updates, 2TB SSD LVM-thin pool, API token |
| `playbooks` | Primary high level orchestration |

## Dev Log
High Level Steps / phases
1. Create VM template
2. Automate cloning of template
3. Automate isntall of RKE2 (WIP)
4. Automate/Setup Storage
5. Automate Jellyfin Install/Configuration
6. Automate MetalLB/ingress creation/config
7. Automate content share and network protection (qBittorrent + NordVPN)

## Configure the Proxmox host

1. On castellan run `lsblk` and find the 2TB SSD. Set `proxmox_vm_disk_device` in `group_vars/proxmox.yml`.
2. Dry run: `ansible-playbook site.yml --check --diff`
3. Real run (repos, updates, automation user): `ansible-playbook site.yml`
4. When ready to format the 2TB SSD (destroys its contents):
   `ansible-playbook site.yml --tags storage -e proxmox_prepare_vm_disk=true`
5. Move the token secret from `.secrets/pve-token.json` into an ansible-vault file
   (see `group_vars/vault.yml.example`), then delete the plaintext.
