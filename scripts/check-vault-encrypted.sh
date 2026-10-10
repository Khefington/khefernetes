#!/usr/bin/env bash
# Fails if any file passed in does not start with the ansible-vault header.
# Used by pre-commit so a plaintext vault can never be committed by accident.
set -eu
rc=0
for f in "$@"; do
  if ! head -n1 "$f" | grep -q '^\$ANSIBLE_VAULT;'; then
    echo "NOT ENCRYPTED: $f  (run: ansible-vault encrypt $f)" >&2
    rc=1
  fi
done
exit $rc
