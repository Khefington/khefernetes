# Ansible variable precedence (cheat sheet)

Lower numbers lose to higher numbers. This repo keeps almost everything in `inventories/group_vars/`
and `host_vars/`, and role defaults hold only tunables with safe values.

1. role `defaults/main.yml` (lowest)
2. inventory `group_vars/all`
3. inventory `group_vars/<group>` (more specific groups beat `all`)
4. inventory `host_vars/<host>`
5. play `vars:` / `vars_files:`
6. role `vars/`, task `vars:`, `set_fact`, `register`
7. `-e` on the command line (highest)

Practical rules used here:
- A variable that more than one group needs belongs in `group_vars/all` (e.g. `template_name`, `proxmox_api_*`, `media_uid`).
  A variable defined in `group_vars/proxmox` is invisible to the cluster VMs, because they are not in that group.
- A value that starts with `{{` must be quoted in YAML.
- A colon followed by a space inside an unquoted string breaks YAML; quote the string.
