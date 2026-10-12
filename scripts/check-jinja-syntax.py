#!/usr/bin/env python3
"""Parse every Jinja expression in the repo (conditions, {{ }} strings, .j2 templates) and report syntax errors.

ansible-lint and --syntax-check do not evaluate 'when:' expressions, so a stray quote only shows up when that task
runs. This catches it early. It checks syntax only: Ansible's own filters (bool, from_json, ...) are not validated.
"""
import glob
import sys

import jinja2
import yaml

env = jinja2.Environment()
CONDITION_KEYS = {"when", "until", "failed_when", "changed_when"}
problems = []
checked = 0


def check(text, where):
    global checked
    checked += 1
    try:
        env.parse(text)
    except jinja2.TemplateSyntaxError as exc:
        problems.append(f"{where}: {exc}\n    {str(text).strip()[:120]!r}")


def walk(node, where):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in CONDITION_KEYS:
                for expr in value if isinstance(value, list) else [value]:
                    if isinstance(expr, str):
                        check("{{ " + expr + " }}", f"{where} ({key})")
            walk(value, where)
    elif isinstance(node, list):
        for item in node:
            walk(item, where)
    elif isinstance(node, str) and ("{{" in node or "{%" in node):
        check(node, where)


yaml_files = [
    f
    for pattern in ("roles/**/*.yml", "playbooks/**/*.yml", "inventories/**/*.yml")
    for f in glob.glob(pattern, recursive=True)
    if not f.endswith("vault.yml")
]
for path in yaml_files:
    with open(path, encoding="utf-8") as handle:
        for document in yaml.safe_load_all(handle):
            walk(document, path)
for path in glob.glob("roles/**/*.j2", recursive=True):
    with open(path, encoding="utf-8") as handle:
        check(handle.read(), path)

print(f"Checked {checked} expressions and templates.")
if problems:
    print("\n".join(problems))
    sys.exit(1)
