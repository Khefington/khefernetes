# Dev log

Kept from the original README. Newest entries go at the bottom.

High Level Steps / phases
1. Create VM template
2. Automate cloning of template
3. Automate isntall of RKE2 (WIP)
4. Automate/Setup Storage
5. Automate Jellyfin Install/Configuration
6. Automate MetalLB/ingress creation/config
7. Automate content share and network protection (qBittorrent + NordVPN)
8. Automate Configuration of RKE2
### Create VM template (DONE)
#### 10/3/2026
1. I'm starting to pick up on the intentions some more and how ansible tends to see content in the repo. The most important thing I've learned is that naming is very intentional and so is directory structure. While ansible is VERY liberal in how it will allow you to structure a repo it will only check for things in a certain way. For example, if you only ever have one target/objective for automation, you could simply make inventories, maybe apply a group_vars folder but then just slap your host files right there. However, if you have a multitude of inventories maybe you split them up into sub directories. More of less, if you define a folder as an inventory, it will look for yml files inside of it, group_vars, groups, and any relevant files inside of those two directories. So in the case of this repo, we have a "cluster," inside of that.....

2. As I was writing the previous I realized that maybe I didn't understand it well enough so I took a deep dive to learn more. An inventory is just a file. In our repo, this could just be anvil or castellan. An inventory has many formats but it's just a yml or ini file to hold content. An inventory file holds a ton of content and is highly configurable. You can add/create groups, hosts, etc. Let's take "anvil.yml" as an example. Inside of it you can see 3 main groups anvil_control_planes, anvil_workers, and anvil_cluster. Inside of some of those groups we define "hosts." There is another group in there that we make by calling referencing the two other groups as its children. 
### Automate cloning of template (DONE)
#### 10/4/2026
1. Took a little longer than anticipated but this section is now complete
### Automate install of RKE2 (DONE)
#### 10/4/2026
1. Took a lot from the homelab stuff that is out there, pretty painless once you put the pieces together
### Automate/Setup Storage (WIP)
#### 10/4/2026
1. Starting now
### Automate Jellyfin Install/Configuration
### Automate MetalLB/ingress creation/config
### Automate content share and network protection (qBittorrent + NordVPN)
### Automate Configuration of RKE2

### 10/9/2026 - restructure
- Moved to a `production` inventory, roles for every concern, thin playbooks, `site.yml`, docs and lint tooling.
- Added books as a library, a media audit (completeness proof), a flatten repair, and Jellyfin diagnostics.
