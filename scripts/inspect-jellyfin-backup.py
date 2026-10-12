#!/usr/bin/env python3
"""Read-only look inside a Jellyfin 10.11 backup zip (the jellyfin-backup-*.zip files in <hdd>/data/backups/jellyfin).

    python3 scripts/inspect-jellyfin-backup.py path/to/jellyfin-backup-20261012125828.zip

It shows what a restore of this zip would put back: the date it was taken, the settings files (including the
hardware-acceleration setting), the profile pictures, the libraries, and how many users, watched / in-progress items and
saved display settings the database holds. Nothing is written anywhere. No third-party packages needed.

Layout of a 10.11 backup zip: Config/ (system.xml, encoding.xml, branding.xml, users/<name>/profile.*),
Root/ (library definitions), Data/ (scheduled tasks, collections, playlists), Database/<Table>.json (one file per table),
manifest.json. A restore OVERWRITES those files and replaces the database with the zip's copy.
"""
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

BIG_TABLE_BYTES = 150_000_000  # do not parse anything larger than this


def rows_of(z, table):
    """Return the rows of Database/<table>.json as a list of dicts, or None if the file is absent/unreadable."""
    name = f"Database/{table}.json"
    if name not in z.namelist():
        return None
    if z.getinfo(name).file_size > BIG_TABLE_BYTES:
        return None
    try:
        data = json.loads(z.read(name))
    except ValueError:
        return None
    if isinstance(data, dict):  # tolerate {"Items": [...]}-style wrappers
        data = next((v for v in data.values() if isinstance(v, list)), [])
    return [r for r in data if isinstance(r, dict)]


def pick(row, *names):
    """Case-insensitive column lookup."""
    lower = {k.lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def xml_value(z, name, tag):
    try:
        return ET.fromstring(z.read(name)).findtext(tag)
    except (KeyError, ET.ParseError):
        return None


def main(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    print(f"Backup: {Path(path).name}")

    manifest = {}
    if "manifest.json" in names:
        manifest = json.loads(z.read("manifest.json"))
        print(f"  taken (UTC): {manifest.get('DateCreated')}")
        print(f"  server version: {manifest.get('ServerVersion')}    backup engine: {manifest.get('BackupEngineVersion')}")
        print(f"  options: {manifest.get('Options')}")
    else:
        print("  no manifest.json: Jellyfin will refuse to restore this file")

    print("\n== Settings files that a restore will overwrite (Config/)")
    for n in sorted(x for x in names if x.startswith("Config/") and not x.endswith("/")):
        print(f"  {z.getinfo(n).file_size:>10,}  {n}")
    hw = xml_value(z, "Config/encoding.xml", "HardwareAccelerationType")
    hwenc = xml_value(z, "Config/encoding.xml", "EnableHardwareEncoding")
    print(f"\n  Hardware acceleration in this backup: {hw!r}   hardware encoding: {hwenc!r}"
          if hw is not None or hwenc is not None else "\n  Hardware acceleration: no encoding.xml in this backup (Jellyfin's default, which is none)")
    sname = xml_value(z, "Config/system.xml", "ServerName")
    if sname is not None:
        print(f"  Server name in system.xml: {sname!r}")
    pics = [n for n in names if n.startswith("Config/users/") and "/profile." in n.lower()]
    print("  Profile pictures: " + (", ".join(pics) if pics else "NONE (a restore will not bring back a picture)"))
    branding = [n for n in names if n.lower().startswith("config/branding") or "splashscreen" in n.lower()]
    print("  Branding / splash screen files: " + (", ".join(branding) if branding else "none"))

    libs = sorted({n.split("/")[2] for n in names if n.startswith("Root/default/") and len(n.split("/")) > 3})
    print(f"\n== Libraries defined in Root/: {libs or 'none'}")

    print("\n== Database (Database/<Table>.json, one file per table)")
    tables = sorted(n[len("Database/"):-len(".json")] for n in names if n.startswith("Database/") and n.endswith(".json"))
    if not tables:
        print("  No Database folder: this zip holds no database, so it cannot restore users or watch history.")
        return 1
    counts = {}
    for t in tables:
        rows = rows_of(z, t)
        counts[t] = len(rows) if rows is not None else "?"
    for t in ["Users", "UserData", "DisplayPreferences", "ItemDisplayPreferences", "CustomItemDisplayPreferences",
              "Preferences", "BaseItems", "AncestorIds", "ApiKeys", "Devices"]:
        if t in counts:
            print(f"  {t:<30}{counts[t]}")

    users = {}
    for r in rows_of(z, "Users") or []:
        users[str(pick(r, "Id"))] = pick(r, "Username", "Name")
    print(f"\n  Users: {sorted(str(u) for u in users.values())}")

    # Profile pictures live in two places: the file (Config/users/<name>/profile.*) and a database row in ImageInfos that
    # ties the file to the user. Jellyfin 10.11 restores the file but can lose the user on that row (jellyfin issue #15829).
    infos = rows_of(z, "ImageInfos")
    if infos is not None:
        user_rows = [r for r in infos if "/users/" in str(pick(r, "Path") or "").replace("\\", "/").lower()]
        print(f"\n  Profile-picture rows in ImageInfos: {len(user_rows)}")
        for r in user_rows:
            owner = pick(r, "UserId")
            print(f"    {pick(r, 'Path')}  -> user: {users.get(str(owner), owner) if owner else 'NONE (not linked)'}")
        if not user_rows and pics:
            print("    The zip has picture FILES but no database row for them: after a restore the picture will not show\n"
                  "    until it is re-attached (`make jellyfin-profile-fix`, which `make jellyfin-restore` runs for you).")

    ud = rows_of(z, "UserData")
    if ud is not None:
        print("\n  Watch state per user (UserData):")
        stats = defaultdict(lambda: [0, 0, 0, 0, ""])
        for r in ud:
            s = stats[str(pick(r, "UserId"))]
            s[0] += 1
            s[1] += 1 if pick(r, "Played") else 0
            s[2] += 1 if (pick(r, "PlaybackPositionTicks") or 0) > 0 else 0
            s[3] += 1 if pick(r, "IsFavorite") else 0
            lp = pick(r, "LastPlayedDate") or ""
            s[4] = max(s[4], str(lp))
        print("    user | rows | played | in progress | favourites | last played")
        for uid, s in sorted(stats.items(), key=lambda kv: str(users.get(kv[0], kv[0]))):
            print(f"    {users.get(uid, uid)} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {s[4]}")
        if not stats:
            print("    none: this backup holds no watch history at all")

    for table, label in [("DisplayPreferences", "Display settings (home screen, view types)"),
                         ("ItemDisplayPreferences", "Per-library / per-item view settings"),
                         ("CustomItemDisplayPreferences", "Custom display preferences")]:
        rows = rows_of(z, table)
        if rows is None:
            continue
        per = defaultdict(int)
        for r in rows:
            per[str(users.get(str(pick(r, "UserId")), pick(r, "UserId")))] += 1
        print(f"\n  {label} rows per user: {dict(per) if per else 'none'}")

    print("\nReading this: a restore replaces the database AND overwrites the files above with the zip's copies.\n"
          "Anything you changed after this backup was taken (see 'taken' above) will be back to how it was then.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
