"""Small helpers for talking to the *arr APIs from Ansible.

Sonarr, Radarr and Prowlarr describe each kind of download client / application / indexer with a "schema" entry: a template
whose `fields` list holds every setting. These filters build the object to send from that template and decide whether an existing
object already matches what Git says, so the playbook only changes what differs.
"""
from __future__ import annotations

import copy

from ansible.errors import AnsibleFilterError

SECRET_PRIVACY = ("password", "apiKey")


def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        return list(a or []) == list(b or [])
    return str(a) == str(b)


def arr_pick(schema, key, value):
    """The schema entry whose `key` equals `value`; a helpful error listing the choices if there is none."""
    for item in schema or []:
        if str(item.get(key)) == str(value):
            return item
    choices = sorted(str(i.get(key)) for i in (schema or []))
    raise AnsibleFilterError("nothing with %s '%s' is offered by the app. Offered: %s" % (key, value, ", ".join(choices)))


def arr_missing_fields(item, wanted):
    """Names in `wanted` that the template has no field for (a typo, or a setting this version does not have)."""
    have = {f.get("name") for f in item.get("fields", [])}
    return sorted(n for n in (wanted or {}) if n not in have)


def arr_secret_fields(item):
    """Names of the fields the app hides when asked (passwords, API keys): their stored value cannot be compared."""
    return sorted(f.get("name") for f in item.get("fields", []) if f.get("privacy") in SECRET_PRIVACY)


def arr_apply(item, wanted, props=None):
    """A copy of `item` with the wanted field values and top-level properties set."""
    out = copy.deepcopy(item)
    wanted = wanted or {}
    for f in out.get("fields", []):
        if f.get("name") in wanted:
            f["value"] = wanted[f["name"]]
    for k, v in (props or {}).items():
        out[k] = v
    return out


def arr_differs(existing, wanted, props=None, secrets=None):
    """True if the existing object differs from Git in a property or a non-secret field."""
    secrets = set(secrets or [])
    for k, v in (props or {}).items():
        if not _same(existing.get(k), v):
            return True
    by_name = {f.get("name"): f.get("value") for f in existing.get("fields", [])}
    for n, v in (wanted or {}).items():
        if n in secrets:
            continue
        if n not in by_name or not _same(by_name[n], v):
            return True
    return False


def arr_dict_diff(current, wanted):
    """The entries of `wanted` whose value differs from `current` (used for qBittorrent's preferences)."""
    return {k: v for k, v in (wanted or {}).items() if k not in (current or {}) or not _same(current[k], v)}


def arr_by_key(items, key):
    """{item[key]: item} for a list of dicts."""
    return {i.get(key): i for i in (items or [])}


class FilterModule:
    def filters(self):
        return {
            "arr_pick": arr_pick,
            "arr_missing_fields": arr_missing_fields,
            "arr_secret_fields": arr_secret_fields,
            "arr_apply": arr_apply,
            "arr_differs": arr_differs,
            "arr_dict_diff": arr_dict_diff,
            "arr_by_key": arr_by_key,
        }
