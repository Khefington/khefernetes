# Sizing: who gets how much of castellan

castellan: i9-12900K (24 hardware threads) and 32 GB RAM. Proxmox itself, the NFS server and the
page cache that makes HDD reads fast all live on the same machine, so roughly 6 GB is kept for the host.

| VM | Role | vCPU | RAM | Why |
|---|---|---|---|---|
| kasrkin | control plane | 2 | 4 GB | etcd and the API server only |
| wyvern | worker, runs Jellyfin | 12 | 16 GB | scans, ffprobe, trickplay and transcoding all happen here |
| basilisk | worker, future apps | 4 | 6 GB | download client, request manager, ... |
| **total** | | 18 | 26 GB | leaves 6 GB RAM for the host |

Set per host in `inventories/host_vars/<host>.yml` (`vm_cores`, `vm_memory_mb`); the default for a host without a file is in `group_vars/anvil_cluster/main.yml`.

## Things worth knowing
- **vCPUs are ceilings, not reservations.** All three VMs share the same 24 hardware threads. Giving wyvern 12 vCPUs does not take them away from basilisk; an idle VM uses nothing. This is also why "move the work to the other worker" would not make anything faster: it is the same physical CPU.
- **Jellyfin cannot be split across nodes.** It is one process with one SQLite database, and its config volume lives on wyvern's disk. Kubernetes can put the pod on a different node, but cannot share the work between nodes. Speed comes from giving that one VM more CPU and RAM.
- Inside wyvern, Jellyfin may use up to 10 GiB (`jellyfin_memory_limit`) and 2 CPUs are reserved for it (`jellyfin_cpu_request`); it can burst above that because there is no CPU limit.

## Applying a size change
`make vms` writes the new numbers into the VM definition. A running VM only picks them up after a full stop and start (a reboot from inside the VM is not enough). One node at a time, on castellan:

    sudo qm shutdown <vm_id> --timeout 180 && sudo qm start <vm_id>

(kasrkin 201, wyvern 202, basilisk 203.) Do the control plane first and wait until `kubectl get nodes` shows it Ready. The Jellyfin pod comes back by itself when wyvern is up.

## Later: hardware transcoding
The 12900K has an Intel iGPU (Quick Sync) that makes transcoding far cheaper than CPU transcoding. Using it from a VM needs PCI passthrough of the iGPU to wyvern. It is a separate project with trade-offs; worth doing when several people stream at once.
