#!/usr/bin/env bash
# Moves an existing checkout from the old layout (inventories/cluster, playbooks/cluster, ...) to this one.
#
# Run it from the root of your OLD repository, pointing at the unzipped NEW tree:
#     bash /path/to/new-tree/scripts/migrate-from-cluster-layout.sh
#
# What it does (it never deletes anything):
#   1. refuses to run if git has uncommitted changes (so you can always get back with git)
#   2. moves the secret vault file to a safe temporary name
#   3. moves every old file into ./_old_layout/ for you to review
#   4. copies the new tree in (keeps .git, .venv and .vault_pass)
#   5. puts the vault file in its new place
set -euo pipefail

new_tree="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$(pwd)"

[ "$new_tree" != "$target" ] || { echo "Run this from your old repository root, not from the new tree." >&2; exit 1; }
[ -d inventories/cluster ] || { echo "inventories/cluster not found: run from the root of the old repository." >&2; exit 1; }
[ ! -d _old_layout ] || { echo "_old_layout already exists; move it away first." >&2; exit 1; }

if [ -d .git ] && [ -n "$(git status --porcelain)" ]; then
  echo "Uncommitted changes found. Commit them first:  git add -A && git commit -m 'before restructure'" >&2
  exit 1
fi

old_vault=inventories/cluster/group_vars/all/vault.yml
stash=""
if [ -f "$old_vault" ]; then
  stash="$(mktemp ./.vault.migrating.XXXXXX)"
  mv "$old_vault" "$stash"
  echo "vault moved aside: $stash"
else
  echo "NOTE: $old_vault not found; you will need to create the new vault (docs/secrets.md)."
fi

mkdir _old_layout
for item in inventories playbooks roles README.md ansible.cfg requirements.txt requirements.yml .gitignore; do
  [ -e "$item" ] && mv "$item" _old_layout/
done

# copy the new tree in; cp -a keeps modes. .git, .venv and .vault_pass in the target are untouched.
(cd "$new_tree" && tar cf - --exclude=.git .) | tar xf - -C "$target"

if [ -n "$stash" ]; then
  mkdir -p inventories/group_vars/all
  mv "$stash" inventories/group_vars/all/vault.yml
  echo "vault restored at inventories/group_vars/all/vault.yml"
fi

cat <<MSG

Done. Old files are in ./_old_layout (review, then remove with: git rm -r --cached _old_layout 2>/dev/null; rm -r _old_layout).
Next:
  1. make setup && source .venv/bin/activate     (or keep your own venv; collections now install into ./collections)
  2. make syntax && make ping
  3. git add -A && git commit -m "Restructure repository"
  4. see docs/MIGRATION.md for renamed variables and the checks to run
MSG
