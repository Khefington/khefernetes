#!/usr/bin/env python3
"""Read-only look inside a Jellyfin database backup zip (the ones in <hdd>/data/backups/jellyfin).

    python3 scripts/inspect-jellyfin-backup.py path/to/jellyfin-backup-....zip

It answers one question: does this backup hold what you expect? It prints what is in the zip, how many users,
watched/in-progress items and saved display settings (home screen layout) the database has, and when it was taken.
Nothing is written anywhere except a temporary copy, which is deleted. No third-party packages needed.
"""
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

# Tables worth looking at first (names as in Jellyfin 10.11's database). Everything else is listed after them.
KEY_TABLES = ["Users", "UserData", "DisplayPreferences", "ItemDisplayPreferences", "CustomItemDisplayPreferences",
              "Preferences", "Permissions", "BaseItems", "AncestorIds", "ImageInfos", "Devices"]


def one(cur, sql):
    try:
        return cur.execute(sql).fetchall()
    except sqlite3.Error as e:
        return f"(could not read: {e})"


def main(path):
    z = zipfile.ZipFile(path)
    print(f"Backup: {Path(path).name}")
    print("\nFiles in the zip:")
    for i in sorted(z.infolist(), key=lambda i: i.filename):
        if not i.is_dir():
            print(f"  {i.file_size:>12,}  {i.filename}")
    for n in z.namelist():
        if n.lower().endswith("manifest.json"):
            print("\nmanifest.json:")
            try:
                print("  " + json.dumps(json.loads(z.read(n)), indent=2).replace("\n", "\n  "))
            except ValueError:
                print("  (not readable as JSON)")
    dbs = [n for n in z.namelist() if n.lower().endswith(".db")]
    if not dbs:
        print("\nNo .db file in this zip: it holds no database, so it cannot restore users or watch history.")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        for name in dbs:
            target = Path(tmp) / Path(name).name
            target.write_bytes(z.read(name))
            print(f"\n=== {name}")
            con = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
            cur = con.cursor()
            tables = [r[0] for r in cur.execute("select name from sqlite_master where type='table' order by name")]
            counts = {}
            for t in tables:
                try:
                    counts[t] = cur.execute(f'select count(*) from "{t}"').fetchone()[0]
                except sqlite3.Error:
                    counts[t] = "?"
            print("Row counts (the ones that matter first):")
            for t in KEY_TABLES + [t for t in tables if t not in KEY_TABLES]:
                if t in counts and (t in KEY_TABLES or counts[t] not in (0, "?")):
                    print(f"  {t:<34}{counts[t]}")
            if "Users" in counts:
                print("\nUsers:", one(cur, 'select Username from Users order by Username'))
            if "UserData" in counts:
                print("\nWatch state per user (UserData):")
                print("  user | rows | played | in progress | favourites | last played")
                sql = ('select u.Username, count(*), sum(d.Played), '
                       'sum(case when d.PlaybackPositionTicks > 0 then 1 else 0 end), sum(d.IsFavorite), max(d.LastPlayedDate) '
                       'from UserData d left join Users u on u.Id = d.UserId group by d.UserId')
                rows = one(cur, sql)
                if isinstance(rows, str):
                    print("  " + rows)
                else:
                    for r in rows:
                        print("  " + " | ".join(str(x) for x in r))
                    if not rows:
                        print("  (none: this backup has no watch history at all)")
            if "DisplayPreferences" in counts:
                print("\nDisplay settings saved per user (home screen layout lives here):")
                rows = one(cur, 'select UserId, Client, ItemId, count(*) from DisplayPreferences group by UserId, Client, ItemId')
                if isinstance(rows, str):
                    print("  " + rows)
                else:
                    for r in rows:
                        print("  " + " | ".join(str(x) for x in r))
                    if not rows:
                        print("  (none)")
            con.close()
    print("\nReading this: users and watch state should be non-zero if the server was used before the backup was taken.\n"
          "If they are zero here, the backup was taken before that use (check its date in the file name), "
          "and no restore could bring it back.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
