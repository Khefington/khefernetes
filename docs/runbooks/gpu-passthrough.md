# Quick Sync for Jellyfin: passing the Intel iGPU to wyvern

**Status:** stage 0 done (castellan is ready: GRUB, IOMMU on, iGPU alone in its IOMMU group, no monitor attached). Stage 1 is done: `make gpu-host` was applied, castellan was rebooted, and the iGPU is bound to `vfio-pci` (status READY). Stage 2 is done: wyvern is on q35 + UEFI and sees the iGPU (`lspci` shows `AlderLake-S GT1 [8086:4680]` at 01:00.0). `make gpu-guest-discover` showed wyvern runs the generic Ubuntu kernel 6.8.0-146 but has no `i915` module and no `linux-firmware`; stage 3 (`make gpu-guest`) installs them. Stage 3 is written and waiting to be applied. Today Jellyfin transcodes in software (`/dev/dri` does not exist in the pod and `intel_gpu_top` on wyvern finds no GPU), even if "Intel QuickSync" is selected in the Dashboard.

## Why this is needed
Jellyfin runs in a container on wyvern, which is a VM. A VM cannot see castellan's integrated GPU unless castellan hands it over (PCIe passthrough with VFIO). After that the VM has its own `/dev/dri`, and the Jellyfin pod can be given that device.
The i9-12900K's UHD 770 does hardware H.264, HEVC (also 10-bit) and VP9 decoding, and H.264 / HEVC encoding. It is much cheaper than software transcoding when several people watch at once.

## The plan, one stage at a time (each stage ends with a check and can be undone)
| Stage | What | Touches | Status |
|---|---|---|---|
| 0 | `make gpu-discover`: read-only report (IOMMU, boot method, the iGPU's IOMMU group, whether a monitor is attached, the VM's current hardware) | nothing | done |
| 1 | VT-d is on (confirmed). `make gpu-host`: kernel options for the IOMMU, VFIO modules, keep `i915` away from the iGPU, rebuild initramfs. Then **you reboot castellan** | castellan boot config | done |
| 2 | wyvern gets the iGPU as a PCIe device (`hostpci0`), on the q35 machine type with UEFI (OVMF); applied by `make vms` | wyvern only (restarted) | done |
| 3 | In wyvern: a kernel with the `i915` driver, firmware, media drivers; check `/dev/dri` and `vainfo`. First `make gpu-guest-discover` (read-only report) | wyvern only | ready to run |
| 4 | Jellyfin pod: mount `/dev/dri`, add the `render` group, set `jellyfin_encoding_config` (QSV), prove with an ffmpeg test | the Jellyfin deployment | last |

The stage 0 report showed: UEFI boot with **GRUB** (not systemd-boot), kernel 6.8.12-43-pve, kernel line `quiet`, the IOMMU is already active (19 groups), the iGPU (`0000:00:02.0`, `8086:4680`) is alone in IOMMU group 0, no monitor is connected, and `vfio-pci` is available. So the kernel options go in `/etc/default/grub`.

## Stage 1 in detail: `make gpu-host`
1. **Plan only (default).** `make gpu-host` writes nothing. It checks that: the host boots with GRUB; `/etc/default/grub` has the expected line; the device at `0000:00:02.0` really is `8086:4680`; its IOMMU group holds exactly that one device; no monitor is connected to it. If any check fails the play stops with the reason. It then prints the kernel line before and after, the files it would write, and the current status.
2. **Apply.** `make gpu-host ARGS="-e gpu_passthrough_prepare=true"` writes four things (every edited file is first copied aside as `file.<number>.<timestamp>~`):
   - `/etc/default/grub`: `quiet` becomes `quiet intel_iommu=on iommu=pt` (existing options are kept, nothing is duplicated).
   - `/etc/initramfs-tools/modules`: a marked block loading `vfio`, `vfio_iommu_type1`, `vfio_pci` early.
   - `/etc/modules-load.d/khefernetes-vfio.conf`: the same three modules at boot.
   - `/etc/modprobe.d/khefernetes-vfio.conf`: `options vfio-pci ids=8086:4680` plus `softdep i915 pre: vfio-pci` and `softdep xe pre: vfio-pci`, so `vfio-pci` claims the iGPU before the Intel graphics drivers can.
   Then it rebuilds the initramfs (`update-initramfs -u -k all`) and then GRUB (`update-grub`). If the initramfs step fails, GRUB is left alone, so castellan still boots as it does today. **It never reboots.**
3. **Before you reboot:** run `make backup-now` and `make etcd-backup-now`. The reboot takes the three VMs, NFS and DNS down for several minutes (risk 3).
4. **After the reboot:** `make gpu-host` again. It reports `READY` when the iGPU is bound to `vfio-pci`, `PENDING REBOOT` when the files are in place but the old driver still owns it, `NOT CONFIGURED` otherwise. Only `READY` means stage 2 can start.
5. If the host does not come up properly, the previous GRUB entries are still in the boot menu (choose an older kernel or edit the line at the GRUB prompt by pressing `e` and deleting `intel_iommu=on iommu=pt`), then follow "If it goes wrong".
6. Another file under `/etc/default/grub.d/` can override the kernel line; the play warns if it finds one. The status report shows the options the running kernel actually has.

## Stage 2 in detail: `make vms`
`inventories/host_vars/wyvern.yml` now says `vm_gpu_passthrough: true`. `make vms` then does, for wyvern only:
1. The normal steps (clone if missing, cores, memory, cloud-init). A VM with the GPU is **not** started here.
2. A new step on castellan (role `proxmox_vm_gpu`) checks that the iGPU is on `vfio-pci` (stage 1 READY), reads wyvern's configuration, and works out what is missing: machine type `q35`, UEFI firmware (`ovmf`) with an EFI disk, `balloon 0` (no memory ballooning), and `hostpci0: 0000:00:02.0,pcie=1`. It uses `qm` over SSH because Proxmox only lets root, not the API token, attach a raw PCI device.
3. If wyvern is **running** and anything is missing, it stops with a message instead of restarting it. When a restart is fine:
   ```
   make backup-now            # Jellyfin backup first
   make vms ARGS="-e proxmox_vm_gpu_allow_restart=true"
   ```
   It then shuts wyvern down cleanly (forced after 3 minutes), applies the settings, starts it and waits for SSH and cloud-init like any rebuild. Jellyfin is down meanwhile (a few minutes); its data stays, the disk is not touched.
4. Running it again changes nothing. A freshly cloned wyvern (after `make destroy-vms`) gets the same settings automatically and is started by this step.

What to check afterwards (on wyvern, over SSH, or `ansible wyvern -a ...`): `lspci -nn | grep -i vga` shows the Intel device. At this point there is probably still no `/dev/dri`, because the guest needs the `i915` driver: that is stage 3. Also `make ping` and `kubectl get nodes` should show wyvern Ready, and Jellyfin should come back by itself.

**Things that can go wrong in stage 2**, all fixable over SSH on castellan:
- *wyvern does not start* (check `qm start 202`, `journalctl -b | grep -i vfio`): usually the iGPU not on `vfio-pci` after a host reboot, a `BAR 0: can't reserve` error (risk 11 below), or not enough free host memory (wyvern's 16 GB is now pinned; the other VMs and castellan need about 10 GB more).
- *wyvern boots but is unreachable*: the switch from the old BIOS/i440fx setup to UEFI/q35 changes how the guest sees its disk and network card. The Ubuntu cloud image supports UEFI and cloud-init names the interface `eth0` by its MAC address, so this should be fine, but it is the one step that changes how the existing VM boots. Revert: `qm stop 202; qm set 202 --delete hostpci0,efidisk0 --bios seabios --machine pc; qm start 202`. Its disk was not changed.
- *Proxmox says the device is in use*: the iGPU is not on `vfio-pci` yet (run `make gpu-host`).

## Stage 3 in detail: `make gpu-guest`
The report (`make gpu-guest-discover`) showed the VM runs the standard `generic` kernel, not a stripped one, but `i915` is not there: Ubuntu keeps GPU drivers in `linux-modules-extra`, which the cloud image does not install, and `linux-firmware` is missing. `make gpu-guest` (role `gpu_guest`, only for VMs with `vm_gpu_passthrough: true`):
1. Checks the VM sees the device `8086:4680`.
2. Installs `linux-image-generic` (pulls in `linux-modules-extra` and `linux-firmware`, and keeps them in step with kernel updates), `linux-modules-extra` for the running kernel, `vainfo`, `intel-gpu-tools` and the Intel media driver (`intel-media-va-driver-non-free` when the repositories offer it, otherwise the free one).
3. Writes `/etc/modules-load.d/khefernetes-i915.conf` so the driver loads at every boot.
4. If the running kernel still has no `i915`, it stops and tells you to reboot (`make gpu-guest ARGS="-e gpu_guest_allow_reboot=true"` reboots wyvern for you; Jellyfin is down meanwhile). With the same kernel version installed as is running, no reboot should be needed.
5. Loads the driver (`modprobe i915`), waits for `/dev/dri/renderD128`, runs `vainfo`, and prints the **render group id** (the Jellyfin pod needs it in stage 4) and the GuC/HuC firmware messages. If the device does not appear it prints the kernel messages and stops.

Nothing in Kubernetes changes and Jellyfin keeps running while the driver loads. `make site` runs this step after `make vms`, so a rebuild gets it too (allowing the reboot, since nothing runs on the new VM yet).

*If something goes wrong:* the first time the driver binds a passthrough GPU is the moment risk 4 (no clean reset) can show. Messages like `ROM ... can't claim; no compatible bridge window` in the kernel log are harmless. If wyvern hangs or the render device never appears: `qm reset 202` on castellan restarts it; paste me the kernel messages the play prints.

## Risks, in plain words
1. **The host loses the iGPU.** A monitor plugged into castellan goes blank once VFIO owns the GPU. Everything is still reachable by SSH and the web UI, but if the network ever breaks you would have no local screen. Keep a second way in (for example a USB-Ethernet adapter or a cheap GPU) in mind before relying on this.
2. **Boot configuration mistakes can leave castellan unbootable.** Stage 1 edits kernel options and the initramfs. I will change one thing at a time, keep a copy of every file before editing it, and keep the old kernel entry. A USB stick with a Proxmox installer or any Linux live image is the recovery tool if it still goes wrong.
3. **Everything on castellan goes down during the reboot**, for a few minutes: the VMs (Jellyfin), NFS and **the DNS server**, so no device in the house resolves names until castellan is back. Choose a quiet time; the router's DNS setting has no fallback.
4. **The iGPU may not reset cleanly.** Intel iGPUs have no proper function-level reset, so after wyvern stops or restarts, the GPU can stay unusable inside the VM until **castellan itself reboots**. Reports for 12th-generation chips are mixed; I cannot promise it behaves. Practical effect: a `make destroy-vms` rebuild might need a host reboot before Quick Sync works again. Jellyfin keeps working in software the whole time.
5. **Memory is locked.** A VM with a passthrough device cannot use ballooning: wyvern's 16 GB is reserved from the moment it starts. With the current sizes (see `docs/sizing.md`) that still leaves castellan about 6 GB.
6. **Only one VM can own the iGPU**, and that VM cannot be live-migrated or snapshotted with its memory. Irrelevant on a single host, but it is why this applies to wyvern only.
7. **Shared IOMMU groups.** If the iGPU shares a group with another device (a USB or SATA controller, say), passing it through would take those too. On Alder Lake the iGPU is normally alone in its group; stage 0 prints the group so we know before changing anything.
8. **The VM's kernel must contain the `i915` driver.** Cloud images sometimes ship a trimmed "virtual" kernel without it; stage 3 checks this and installs the full one if needed.
9. **A slightly larger attack surface.** The Jellyfin pod gets the GPU's render device (a non-privileged device node, in the `render` group). That is the usual way to do it, but it matters for the later hardening pass before the server is exposed to the internet.
10. **A connected monitor stays blank.** Once `vfio-pci` owns the iGPU, nothing on castellan can draw to a monitor plugged into it. The GRUB menu still shows (the firmware draws it before the kernel starts), so editing the kernel line at the GRUB prompt still works; after that the screen is dark. A monitor that is plugged in but off or asleep usually reads as "disconnected" and does not stop `make gpu-host`; one that reads "connected" does (override: `gpu_passthrough_allow_display`). Use SSH or the Proxmox web UI to check the host.
11. **The iGPU is castellan's boot display**, the hardest kind to hand to a VM. If wyvern fails to start with a message like `BAR 0: can't reserve` or `Cannot reserve ... efifb`, add `video=efifb:off` to `gpu_passthrough_kernel_options` (role defaults), run `make gpu-host ARGS="-e gpu_passthrough_prepare=true"` and reboot castellan. It is not added by default because it is often unnecessary.
12. **BIOS quirks.** Some boards behave oddly when the iGPU is the primary display, or need "Above 4G decoding" or similar. Stage 0 cannot see those; if the VM will not start after stage 2, this is the first thing to look at.

## If it goes wrong (works over SSH, no screen needed)
1. Remove the passthrough from the VM: `qm set 202 --delete hostpci0` (or re-run `make vms` after taking `hostpci0` out of the inventory).
2. Put the host back (all over SSH):
   ```
   rm /etc/modprobe.d/khefernetes-vfio.conf /etc/modules-load.d/khefernetes-vfio.conf
   # in /etc/initramfs-tools/modules delete the block between "# BEGIN khefernetes vfio" and "# END khefernetes vfio"
   # in /etc/default/grub change the line back to GRUB_CMDLINE_LINUX_DEFAULT="quiet"  (the .<timestamp>~ copy next to it is the original)
   update-initramfs -u -k all && update-grub
   reboot
   ```
3. Set `jellyfin_encoding_config` back to `HardwareAccelerationType: none` and run `make jellyfin-provision`. Jellyfin transcodes in software again, as it does today.

## Not doing
- **Software transcoding forever** is a fine answer for one to three simultaneous streams; the 12 vCPUs on wyvern handle that. This whole project is for several concurrent transcodes and for lower CPU use.
- **Sharing the GPU with a container on the host (LXC)** would avoid VFIO but would mean running Jellyfin outside Kubernetes. It does not fit this repo.
