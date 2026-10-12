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

### 10/11/2026 - rebuild drill findings
- Jellyfin crashed on a fresh config volume: the trickplay mount inside /config made the runtime create /config/data as root. An init container now creates it and hands it to the media user.
- Backup folder on the HDD is mounted into the pod, so the Dashboard's Backups page lists the nightly zips and writes new ones straight to the HDD.
- Restore left artwork blank: the metadata folder is not in a Jellyfin backup. Metadata, subtitles and attachments now persist on the SSD with trickplay (`jellyfin_persisted_dirs`).
- VM sizes set per host (wyvern 12 vCPU / 16 GB for Jellyfin); Jellyfin limit raised to 10 GiB.
- Added `jellyfin_provision`: wizard, plugins (Open Subtitles, Intro Skipper), settings, libraries, users and the backup API key from Git.
- Open Subtitles credentials now come from the vault through `jellyfin_plugin_settings`. The settings viewer hides secret-looking names more precisely (it no longer masks Intro Skipper's `SnapToKeyframe`).
- Added `dns_server` (`make dns`): dnsmasq on castellan answers `*.home.lan` with the ingress address, machine names from the inventory, and forwards everything else. The router's DNS setting then points at castellan. `ingress_vip` moved to `group_vars/all/main.yml` because castellan needs it.
- Added the Bookshelf plugin (13.0.0.0, official catalogue) for the Books library. It is deprecated by Jellyfin 12.0, which has the features built in; remove it before that upgrade. The backup-key Secret now uses `data:` (base64) so `kubectl apply` reports unchanged on a re-run (`stringData` always showed as changed).
- `make k8s-storage` now ends with a storage self-test: one pod per node checks the NFS volumes (NFS, write/read, owner 1500:1500), the downloads->media hardlink, the read-only library view and the node-local volume (local disk, file locking). Also fixed the 'claims Bound' wait: it counted every claim in `media`, so it would have failed on a re-run after Jellyfin existed; it now counts only the static NFS claims.
- `jellyfin_scheduled_task_triggers`: scheduled-task triggers (for example Scan Media Library on startup) are now applied by `make jellyfin-provision`, additively. `jellyfin_provision_show_tasks=true` lists the tasks and their triggers. The mock server now knows scheduled tasks and Bookshelf.
- Added `make jellyfin-restore-settings`: stops Jellyfin, swaps in `config/` and `root/` from a chosen `jellyfin-settings-*.tgz` (current folders kept as `*.before-restore-<time>`), starts Jellyfin again. Profile pictures live in `/config/config/users/<name>/profile.png`, outside the database, so the Dashboard restore never brought them back. Added `scripts/inspect-jellyfin-backup.py` to see what a database zip really holds (users, watch state, display settings).
- Correction: Jellyfin 10.11's backup zip DOES contain the settings files (`Config/`, including `encoding.xml` and profile pictures) and the library definitions (`Root/`), and a restore overwrites them. I had assumed it held only the database, built `make jellyfin-restore-settings` on that, and then removed it again. `scripts/inspect-jellyfin-backup.py` now reads the real zip layout (per-table JSON in `Database/`).
- `jellyfin_encoding_config`: playback / transcoding (hardware acceleration) settings can be declared in the repo and are re-applied by `make jellyfin-provision`. Left empty on purpose: Quick Sync needs the Intel iGPU passed through to wyvern and /dev/dri mounted into the pod, which is not built yet.
- Quick Sync: `/dev/dri` does not exist in the pod and wyvern has no GPU, so Jellyfin was transcoding in software even with QSV selected. Added `make gpu-discover` (read-only report on IOMMU, boot method, the iGPU's IOMMU group) and `docs/runbooks/gpu-passthrough.md` (staged plan, risks, revert). No change has been made to castellan.
- Quick Sync stage 1: `make gpu-host` (role `gpu_passthrough`, vars in `group_vars/all/gpu.yml`). Default run only checks (GRUB boot, device id, iGPU alone in its IOMMU group, no monitor) and prints the plan; `ARGS="-e gpu_passthrough_prepare=true"` adds `intel_iommu=on iommu=pt`, VFIO modules, a vfio-pci bind for 8086:4680 and rebuilds initramfs then GRUB. It never reboots; a status report says READY / PENDING REBOOT / NOT CONFIGURED. Castellan is not changed until you run it.
- Quick Sync stage 1 applied on castellan: GRUB line `quiet intel_iommu=on iommu=pt`, VFIO modules, iGPU bound to vfio-pci after the reboot (READY). Fixed a false 'initramfs has vfio: no' in the status report (`grep -q` closing the pipe early under `pipefail`; it now counts matches). Runbook notes on a connected-but-off monitor and on the boot-display `efifb` option.
- Quick Sync stage 2 (written, not yet applied): `vm_gpu_passthrough: true` in `host_vars/wyvern.yml`; role `proxmox_vm_gpu` runs on castellan inside `make vms` and sets machine q35, OVMF + EFI disk, balloon 0 and `hostpci0: 0000:00:02.0,pcie=1` with `qm` over SSH (only root@pam may attach a raw PCI device through the API). It refuses unless the iGPU is on vfio-pci, and it will not stop a running VM unless `-e proxmox_vm_gpu_allow_restart=true` is given. VMs with the GPU are started by this step, not by the clone step, so a rebuild reproduces the setup.
- Quick Sync stage 2 applied: wyvern sees the iGPU (`01:00.0 VGA ... AlderLake-S GT1 [8086:4680]`). Added `make gpu-guest-discover` (read-only report from inside wyvern: kernel flavour, i915 availability, firmware, /dev/dri) to decide stage 3.
- Quick Sync stage 3 (written): `make gpu-guest` (role `gpu_guest`, also in `site.yml` after the VMs). wyvern's generic kernel had no i915 (GPU drivers are in linux-modules-extra) and no linux-firmware. The role installs linux-image-generic (pulls both), vainfo, intel-gpu-tools and the Intel media driver, loads i915 at boot, loads it now, and proves /dev/dri/renderD128 with vainfo; it reboots only with `-e gpu_guest_allow_reboot=true` (site.yml sets it for a fresh VM). The GPU vars moved to `group_vars/all/gpu.yml` because the VM needs the PCI id too.
- Quick Sync stage 3 applied on wyvern: `/dev/dri/renderD128` (render gid 992), GuC/HuC firmware loaded, HuC authenticated, vainfo shows iHD with the low-power H.264 encode path.
- Quick Sync stage 4 (written): role `intel_gpu_plugin` (`make gpu-plugin`, Intel GPU device plugin 0.36.0 in its own namespace, only on GPU nodes, shared by 2 containers), Jellyfin pod requests `gpu.intel.com/i915: 1` and joins the render group (a mounted /dev/dri alone is blocked by the container runtime for unprivileged pods), `make jellyfin-gpu-test` proves QSV encode/decode inside the pod with Jellyfin's ffmpeg, `jellyfin_encoding_config` now holds the QSV settings. `make site` runs them in order and stops at the proof before QSV is switched on.
- Quick Sync first real playback: intel_gpu_top on wyvern showed VCS ~97-100%, VECS ~67%, RCS ~85% (hardware transcoding), but Jellyfin's playback info does not label hardware (earlier advice to look for '(hw)' was wrong). Added `make jellyfin-transcode-check` (read-only; reads the newest FFmpeg.Transcode-*.log in the pod and reports -hwaccel / codec flags / Stream mapping).
