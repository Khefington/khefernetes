# Quick Sync for Jellyfin: passing the Intel iGPU to wyvern

**Status:** planned, nothing on castellan has been changed yet. Today Jellyfin transcodes in software (`/dev/dri` does not exist in the pod and `intel_gpu_top` on wyvern finds no GPU), even if "Intel QuickSync" is selected in the Dashboard.

## Why this is needed
Jellyfin runs in a container on wyvern, which is a VM. A VM cannot see castellan's integrated GPU unless castellan hands it over (PCIe passthrough with VFIO). After that the VM has its own `/dev/dri`, and the Jellyfin pod can be given that device.
The i9-12900K's UHD 770 does hardware H.264, HEVC (also 10-bit) and VP9 decoding, and H.264 / HEVC encoding. It is much cheaper than software transcoding when several people watch at once.

## The plan, one stage at a time (each stage ends with a check and can be undone)
| Stage | What | Touches | Status |
|---|---|---|---|
| 0 | `make gpu-discover`: read-only report (IOMMU, boot method, the iGPU's IOMMU group, whether a monitor is attached, the VM's current hardware) | nothing | ready |
| 1 | BIOS: turn on VT-d. Host: kernel options for the IOMMU, VFIO modules, keep `i915` away from the iGPU, rebuild initramfs, **reboot castellan** | castellan boot config | after you read stage 0's output |
| 2 | wyvern gets the iGPU as a PCIe device (`hostpci0`); VM rebuilt through `make vms` | wyvern only | after stage 1 works |
| 3 | In wyvern: a kernel with the `i915` driver, firmware, media drivers; check `/dev/dri` and `vainfo` | wyvern only | after stage 2 |
| 4 | Jellyfin pod: mount `/dev/dri`, add the `render` group, set `jellyfin_encoding_config` (QSV), prove with an ffmpeg test | the Jellyfin deployment | last |

I will not run stages 1 and 2 until the stage 0 report shows what this particular machine needs (GRUB or systemd-boot decides where the kernel options go, and the IOMMU group decides whether it is safe at all).

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
10. **BIOS quirks.** Some boards behave oddly when the iGPU is the primary display, or need "Above 4G decoding" or similar. Stage 0 cannot see those; if the VM will not start after stage 2, this is the first thing to look at.

## If it goes wrong (works over SSH, no screen needed)
1. Remove the passthrough from the VM: `qm set 202 --delete hostpci0` (or re-run `make vms` after taking `hostpci0` out of the inventory).
2. Put the host back: delete the repo-written files under `/etc/modprobe.d/` (`khefernetes-vfio.conf`) and `/etc/modules-load.d/`, remove the kernel options I added (the stage 1 play prints exactly which), `update-initramfs -u -k all`, reboot.
3. Set `jellyfin_encoding_config` back to `HardwareAccelerationType: none` and run `make jellyfin-provision`. Jellyfin transcodes in software again, as it does today.

## Not doing
- **Software transcoding forever** is a fine answer for one to three simultaneous streams; the 12 vCPUs on wyvern handle that. This whole project is for several concurrent transcodes and for lower CPU use.
- **Sharing the GPU with a container on the host (LXC)** would avoid VFIO but would mean running Jellyfin outside Kubernetes. It does not fit this repo.
