# Everything is driven through ansible.cfg (inventory, vault password file, roles path).
# `make help` lists the targets. Run from the repository root.

# Extra ansible-playbook options for any target:  make jellyfin-provision ARGS="-e some_var=value"
# (Plain `make target -e var=value` does not work: make keeps -e for itself and never passes it on.)
ARGS     ?=
PLAYBOOK := ansible-playbook $(ARGS)
VENV     := .venv

.DEFAULT_GOAL := help
.PHONY: help setup lint yamllint jinja ansible-lint syntax ping site proxmox-api \
        proxmox-template gpu-discover gpu-host gpu-guest-discover gpu-guest gpu-plugin dns vms destroy-vms nfs rke2 etcd-backup etcd-backup-now networking k8s-storage jellyfin jellyfin-provision jellyfin-backup backup-now \
        audit-media import-media flatten-media diagnose-jellyfin jellyfin-gpu-test jellyfin-transcode-check jellyfin-restore jellyfin-upgrade-check jellyfin-upgrade jellyfin-upgrade-finish jellyfin-rollback jellyfin-upgrade-cleanup jellyfin-profile-check jellyfin-profile-fix arr arr-provision arr-vpn-test arr-backup arr-backup-now arr-restore security-audit host-firewall host-firewall-apply host-firewall-off host-watchdog host-watchdog-apply host-watchdog-off cluster-hardening cluster-hardening-apply cluster-hardening-off wireguard wireguard-client wireguard-off ddns ddns-status rebuild

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv, install Python packages and Ansible collections (into ./collections)
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/ansible-galaxy collection install -r requirements.yml -p collections
	@echo "Now run:  source $(VENV)/bin/activate"

lint: yamllint ansible-lint jinja ## Run every linter
yamllint: ## YAML style
	yamllint .
jinja: ## Jinja syntax of every condition and template (catches stray quotes in when:)
	python3 scripts/check-jinja-syntax.py
ansible-lint: ## Ansible best practices (production profile)
	ansible-lint
syntax: ## Syntax-check every playbook
	@for p in playbooks/site.yml playbooks/ping.yml playbooks/*/*.yml; do echo "== $$p"; $(PLAYBOOK) --syntax-check $$p >/dev/null || exit 1; done

ping: ## Can Ansible reach every host?
	$(PLAYBOOK) playbooks/ping.yml
site: ## Run the whole build in order
	$(PLAYBOOK) playbooks/site.yml

rebuild: ## After destroy-vms: build everything, restore Jellyfin (asks RESTORE), harden, VPN, first backups, audit (ARGS="-e rebuild_restore=false" on a first build)
	$(PLAYBOOK) playbooks/rebuild.yml

proxmox-api: ## Create/refresh the Proxmox API role, user and token (add ARGS="-e proxmox_bootstrap_rotate_token=true" to rotate)
	$(PLAYBOOK) playbooks/proxmox/bootstrap.yml --tags api
proxmox-template: ## Build the VM template
	$(PLAYBOOK) playbooks/proxmox/template.yml
destroy-vms: ## DELETE the three cluster VMs (asks you to type DESTROY); data on castellan is untouched
	$(PLAYBOOK) playbooks/cluster/destroy_vms.yml
gpu-discover: ## READ-ONLY report: is castellan ready to pass the Intel iGPU to wyvern? (read docs/runbooks/gpu-passthrough.md first)
	$(PLAYBOOK) playbooks/proxmox/gpu_discover.yml
gpu-host: ## Stage 1: check castellan and show the plan; apply with ARGS="-e gpu_passthrough_prepare=true" (never reboots)
	$(PLAYBOOK) playbooks/proxmox/gpu_host.yml
gpu-guest-discover: ## READ-ONLY report from inside wyvern: kernel, i915 driver, firmware, /dev/dri (stage 3)
	$(PLAYBOOK) playbooks/cluster/gpu_guest_discover.yml
gpu-guest: ## Stage 3: i915 driver, firmware and media driver inside wyvern; proves /dev/dri works (no reboot unless ARGS="-e gpu_guest_allow_reboot=true")
	$(PLAYBOOK) playbooks/cluster/gpu_guest.yml
gpu-plugin: ## Stage 4a: Intel GPU device plugin in the cluster (pods can then request the GPU)
	$(PLAYBOOK) playbooks/cluster/gpu_plugin.yml
dns: ## DNS server on castellan: *.home.lan -> the ingress (then point the router at castellan)
	$(PLAYBOOK) playbooks/proxmox/dns.yml
vms: ## Clone the template into the cluster VMs
	$(PLAYBOOK) playbooks/cluster/create_vms.yml
nfs: ## NFS server on castellan, clients on the VMs, mount tests
	$(PLAYBOOK) playbooks/storage/nfs.yml
rke2: ## Install RKE2
	$(PLAYBOOK) playbooks/cluster/rke2.yml
etcd-backup: ## Install the timer that copies etcd snapshots to castellan
	$(PLAYBOOK) playbooks/cluster/etcd_backup.yml
etcd-backup-now: ## Take an etcd snapshot now, copy it to castellan and prove it arrived
	$(PLAYBOOK) playbooks/cluster/etcd_backup.yml -e etcd_backup_take_snapshot_now=true
networking: ## MetalLB and the ingress LoadBalancer address
	$(PLAYBOOK) playbooks/cluster/networking.yml
k8s-storage: ## Namespace, NFS volumes, local-path provisioner, then a self-test pod on every node (skip: ARGS="-e k8s_storage_run_test=false")
	$(PLAYBOOK) playbooks/storage/kubernetes.yml
jellyfin: ## Deploy Jellyfin
	$(PLAYBOOK) playbooks/apps/jellyfin.yml
jellyfin-gpu-test: ## Stage 4c: prove Quick Sync works inside the running Jellyfin pod (ffmpeg QSV encode/decode)
	$(PLAYBOOK) playbooks/apps/jellyfin_gpu_test.yml
jellyfin-transcode-check: ## READ-ONLY: did the latest playbacks use the GPU? (reads Jellyfin's transcode logs)
	$(PLAYBOOK) playbooks/apps/jellyfin_transcode_check.yml
jellyfin-restore: ## Restore Jellyfin from its newest backup (asks you to type RESTORE), then re-provision + re-attach pictures
	$(PLAYBOOK) playbooks/apps/jellyfin_restore.yml
jellyfin-upgrade-check: ## READ-ONLY: is Jellyfin ready for the major upgrade in versions.yml? (blockers, warnings, plugins to remove, disk room)
	$(PLAYBOOK) playbooks/apps/jellyfin_upgrade_check.yml
jellyfin-upgrade: ## Upgrade Jellyfin 10.11 -> 12: backup, copy the config volume, migrate, re-provision (asks you to type UPGRADE)
	$(PLAYBOOK) playbooks/apps/jellyfin_upgrade.yml
jellyfin-upgrade-finish: ## Carry on after an upgrade that only stopped because the migration was slow (settings, scan, backup, GPU test)
	$(PLAYBOOK) playbooks/apps/jellyfin_upgrade_finish.yml
jellyfin-rollback: ## Undo a failed upgrade from the volume copy:  make jellyfin-rollback JELLYFIN_OLD=10.11.11 (asks you to type ROLLBACK)
	$(PLAYBOOK) playbooks/apps/jellyfin_rollback.yml -e jellyfin_rollback_version=$(JELLYFIN_OLD)
jellyfin-upgrade-cleanup: ## Delete the config-volume copies the upgrade left on the node (asks you to type DELETE)
	$(PLAYBOOK) playbooks/apps/jellyfin_upgrade_cleanup.yml
arr: ## Download stack: qBittorrent behind NordVPN, Sonarr, Radarr, Prowlarr (needs the vault secrets in docs/runbooks/download-stack.md)
	$(PLAYBOOK) playbooks/apps/arr.yml
arr-provision: ## Configure the download stack from Git: sign-in, root folders, download client, Prowlarr links and indexers
	$(PLAYBOOK) playbooks/apps/arr_provision.yml
arr-vpn-test: ## READ-ONLY: prove the downloader leaves through NordVPN (public address, no LAN access, tunnel DNS)
	$(PLAYBOOK) playbooks/apps/arr_vpn_test.yml
arr-backup: ## Install the nightly backup job for Sonarr, Radarr and Prowlarr
	$(PLAYBOOK) playbooks/apps/arr_backup.yml
arr-backup-now: ## Install the arr backup job and run one backup right now
	$(PLAYBOOK) playbooks/apps/arr_backup.yml -e arr_backup_run_now=true
arr-restore: ## Restore Sonarr, Radarr and Prowlarr from their newest backup zips (asks you to type RESTORE)
	$(PLAYBOOK) playbooks/apps/arr_restore.yml
jellyfin-profile-check: ## READ-ONLY: are users' profile pictures linked? (shows picture files found in the pod)
	$(PLAYBOOK) playbooks/apps/jellyfin_user_images.yml
jellyfin-profile-fix: ## Re-attach profile pictures that are on disk but no longer linked to their user
	$(PLAYBOOK) playbooks/apps/jellyfin_user_images.yml -e jellyfin_user_images_apply=true
host-firewall: ## Hardening: show the host firewall rules for castellan + VMs and have nft check them (changes nothing)
	$(PLAYBOOK) playbooks/hardening/hosts.yml
host-firewall-apply: ## Hardening: apply the host firewall + castellan's automatic security updates (automatic rollback if contact is lost)
	$(PLAYBOOK) playbooks/hardening/hosts.yml -e host_firewall_apply=true
host-firewall-off: ## Emergency: stop the host firewall on castellan and every VM
	ansible proxmox:anvil_cluster -b -m ansible.builtin.systemd -a "name=khef-firewall state=stopped enabled=false"
host-watchdog: ## READ-ONLY: is castellan set to restart itself after a lockup? (watchdog devices, crash settings, memory speed, crash records)
	$(PLAYBOOK) playbooks/hardening/host_watchdog.yml
host-watchdog-apply: ## Make castellan restart itself after a crash/lockup and log to disk often (hardware watchdog active after the next reboot)
	$(PLAYBOOK) playbooks/hardening/host_watchdog.yml -e host_watchdog_apply=true
host-watchdog-off: ## Undo host-watchdog-apply
	$(PLAYBOOK) playbooks/hardening/host_watchdog.yml -e host_watchdog_off=true
cluster-hardening: ## Hardening: pod-security labels + media NetworkPolicies, plan only (API server dry run)
	$(PLAYBOOK) playbooks/hardening/cluster.yml
cluster-hardening-apply: ## Hardening: apply them, probe the result, roll the policies back automatically if something critical breaks
	$(PLAYBOOK) playbooks/hardening/cluster.yml -e k8s_hardening_apply=true
cluster-hardening-off: ## Emergency: remove the media NetworkPolicies again
	$(PLAYBOOK) playbooks/hardening/cluster.yml -e k8s_hardening_remove=true
security-audit: ## READ-ONLY: security findings for castellan, the VMs, the cluster and Jellyfin's settings
	$(PLAYBOOK) playbooks/operations/security_audit.yml
jellyfin-provision: ## Configure Jellyfin from Git: wizard, plugins, libraries, users, backup key
	$(PLAYBOOK) playbooks/apps/jellyfin_provision.yml
jellyfin-backup: ## Install the nightly Jellyfin backup job
	$(PLAYBOOK) playbooks/apps/jellyfin_backup.yml
backup-now: ## Run one Jellyfin backup immediately (test)
	$(PLAYBOOK) playbooks/apps/jellyfin_backup.yml -e jellyfin_backup_run_now=true

import-media: ## Copy media from the Windows PC to the HDD
	$(PLAYBOOK) playbooks/operations/import_media.yml
audit-media: ## Read-only: prove nothing is missing (or list what is)
	$(PLAYBOOK) playbooks/operations/audit_media.yml
flatten-media: ## Report nested library folders (add APPLY=1 to fix them)
	$(PLAYBOOK) playbooks/operations/flatten_media.yml $(if $(APPLY),-e media_import_apply_flatten=true,)
diagnose-jellyfin: ## Read-only Jellyfin file-access and trickplay health check
	$(PLAYBOOK) playbooks/operations/diagnose_jellyfin.yml
wireguard: ## VPN: WireGuard server on castellan (keys made on castellan, devices from group_vars/all/wireguard.yml)
	$(PLAYBOOK) playbooks/hardening/wireguard.yml
wireguard-client: ## VPN: print one device's config + QR code, e.g. make wireguard-client PEER=phone
	@test -n "$(PEER)" || { echo "Say which device: make wireguard-client PEER=<name>"; exit 2; }
	$(PLAYBOOK) playbooks/hardening/wireguard_client.yml -e wireguard_client_peer=$(PEER)
wireguard-off: ## Emergency: stop the VPN on castellan (devices lose access; the LAN is unaffected)
	ansible proxmox -b -m ansible.builtin.systemd_service -a "name=wg-quick@wg0 state=stopped enabled=false"
ddns: ## VPN: keep a DuckDNS name pointed at your home IP (timer on castellan; needs the name + vault_duckdns_token)
	$(PLAYBOOK) playbooks/hardening/ddns.yml
ddns-status: ## VPN: show when the DuckDNS name was last updated
	ansible proxmox -b -m ansible.builtin.command -a "journalctl -u khef-ddns -n 5 --no-pager"
