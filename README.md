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

## Ansible Precedence
Everything below the former overwrites the former. I.E. Role defaults is overwritten by inventory group_vars/all

1.	role defaults/	(lowest)
2.	inventory group_vars/all	lost to the playbook's all
3.	playbook group_vars/all	beat inventory all
4.	inventory group_vars/<specific group>	beat playbook all for castellan
5.	playbook group_vars/<specific group>	
6.	host vars (inventory, then playbook)	
7.	play vars: and vars_files:	
8.	role vars/, task vars, set_fact	
9.	-e on the command line	beat everything in my test

## Repository Layout
repo/
├ansible.cfg                      # config for ansible, can define defaults and other vars here
├README.md                        # You are here | general info about the repo
├requirements.txt
├requirements.yml
├.vault_pass                      # Encrypted file for the vault password, no need to type it each run
├inventories/                     # the hosts, groups, etc. However you want to define it
├── cluster/                      # renamed from "cluster", since it covers the whole lab
│   ├── anvil.yml                 # the hypervisor host(s)
│   ├── castellan.yml                  # the RKE2 VMs and their groups
│   └── group_vars/
│       ├── all/
│       │   ├── vars.yml          # Things almost everything in the cluster needs to know
│       │   └── vault.yml         # secrets every inventory in cluster shares
│       ├── proxmox/
│       │   ├── vars.yml          # Vars specific to the proxmox group
│       │   └── vault.yml         # Secret vars specific to proxmox
│       └── anvil_cluster/
│           ├── vars.yml          # Vars specific to the anvil_cluster
│           └── vault.yml         # Secret vars specific to anvil_cluster
├playbooks/                       # The plays to run, long term organized futher
├───create_media_server.yml
├───ping.yml
├─── cluster/
│   └── group_vars/
│      └── all/
│         └── all.yml
├roles/                          # The "nouns" to perform actions on, install, remove, etc.
├───create_media_server.yml
├───ping.yml


## Dev Log
High Level Steps / phases
1. Create VM template
2. Automate cloning of template
3. Automate isntall of RKE2 (WIP)
4. Automate/Setup Storage
5. Automate Jellyfin Install/Configuration
6. Automate MetalLB/ingress creation/config
7. Automate content share and network protection (qBittorrent + NordVPN)
### Create VM template
#### 10/3/2026
2. As I was writing the previous I realized that maybe I didn't understand it well enough so I took a deep dive to learn more. An inventory is just a file. In our repo, this could just be anvil or castellan. An inventory has many formats but it's just a yml or ini file to hold content. An inventory file holds a ton of content and is highly configurable. You can add/create groups, hosts, etc. Let's take "anvil.yml" as an example. Inside of it you can see 3 main groups anvil_control_planes, anvil_workers, and anvil_cluster. Inside of some of those groups we define "hosts." There is another group in there that we make by calling referencing the two other groups as its children. 


1. I'm starting to pick up on the intentions some more and how ansible tends to see content in the repo. The most important thing I've learned is that naming is very intentional and so is directory structure. While ansible is VERY liberal in how it will allow you to structure a repo it will only check for things in a certain way. For example, if you only ever have one target/objective for automation, you could simply make inventories, maybe apply a group_vars folder but then just slap your host files right there. However, if you have a multitude of inventories maybe you split them up into sub directories. More of less, if you define a folder as an inventory, it will look for yml files inside of it, group_vars, groups, and any relevant files inside of those two directories. So in the case of this repo, we have a "cluster," inside of that.....

### Automate cloning of template
### Automate isntall of RKE2 (WIP)
### Automate/Setup Storage
### Automate Jellyfin Install/Configuration
### Automate MetalLB/ingress creation/config
### Automate content share and network protection (qBittorrent + NordVPN)
