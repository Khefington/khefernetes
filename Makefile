# Everything is driven through ansible.cfg (inventory, vault password file, roles path).
# `make help` lists the targets. Run from the repository root.

PLAYBOOK := ansible-playbook
VENV     := .venv

.DEFAULT_GOAL := help
.PHONY: help setup lint yamllint ansible-lint syntax ping site \
        proxmox-template vms nfs rke2 k8s-storage jellyfin jellyfin-backup backup-now \
        audit-media import-media flatten-media diagnose-jellyfin

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv, install Python packages and Ansible collections (into ./collections)
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/ansible-galaxy collection install -r requirements.yml -p collections
	@echo "Now run:  source $(VENV)/bin/activate"

lint: yamllint ansible-lint ## Run every linter
yamllint: ## YAML style
	yamllint .
ansible-lint: ## Ansible best practices (production profile)
	ansible-lint
syntax: ## Syntax-check every playbook
	@for p in playbooks/site.yml playbooks/ping.yml playbooks/*/*.yml; do echo "== $$p"; $(PLAYBOOK) --syntax-check $$p >/dev/null || exit 1; done

ping: ## Can Ansible reach every host?
	$(PLAYBOOK) playbooks/ping.yml
site: ## Run the whole build in order
	$(PLAYBOOK) playbooks/site.yml

proxmox-template: ## Build the VM template
	$(PLAYBOOK) playbooks/proxmox/template.yml
vms: ## Clone the template into the cluster VMs
	$(PLAYBOOK) playbooks/cluster/create_vms.yml
nfs: ## NFS server on castellan, clients on the VMs, mount tests
	$(PLAYBOOK) playbooks/storage/nfs.yml
rke2: ## Install RKE2
	$(PLAYBOOK) playbooks/cluster/rke2.yml
k8s-storage: ## Namespace, NFS volumes and the local-path provisioner
	$(PLAYBOOK) playbooks/storage/kubernetes.yml
jellyfin: ## Deploy Jellyfin
	$(PLAYBOOK) playbooks/apps/jellyfin.yml
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
