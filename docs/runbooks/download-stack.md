# The download stack: qBittorrent behind NordVPN, Sonarr, Radarr, Prowlarr

Everything is declared in Git and built by `make arr` + `make arr-provision`; nothing needs clicking through a setup wizard.

```
 Prowlarr ──(indexers, pushed)──► Sonarr ──(sends a torrent)──┐
 (media ns)                      Radarr ──(sends a torrent)──►│  qBittorrent ◄─► Gluetun ══ WireGuard ══► NordVPN (United States)
                                  (media ns)                  └─ (downloads ns: one pod, one network, nothing leaves except the tunnel)
 finished download: /data/downloads/tv/...  ──hardlink──►  /data/media/tv/...   (same share, so no copy and no extra space)
```

## What runs where
| Piece | Namespace | Why |
|---|---|---|
| qBittorrent + Gluetun (one pod) | `downloads` | The pod's network is Gluetun's tunnel. If the tunnel drops, qBittorrent has no connection at all (no "leak"). The namespace is `privileged` for pod security because Gluetun needs `NET_ADMIN`; a network policy lets it send nothing but the WireGuard packets to NordVPN. |
| Sonarr, Radarr, Prowlarr | `media` | Normal pod security (baseline). They reach the internet on 80/443 and each other; not your LAN. |
| Config databases | node-local `local-path` volumes | They are SQLite; SQLite does not work on NFS. The nightly backup (below) is what protects them. |
| Downloads | HDD share, folder `downloads/` | qBittorrent sees **only** `downloads/` (not your library). Sonarr/Radarr see the whole data share, so importing is a hardlink. |
| In-progress downloads | SSD staging share, `/incomplete` | Finished ones are moved to the HDD. |
| Backups | HDD, `backups/arr/<app>-<date>.zip` | Next to Jellyfin's backups; survives `make destroy-vms`. |

All web pages are LAN-only (`sonarr.home.lan`, `radarr.home.lan`, `prowlarr.home.lan`, `qbittorrent.home.lan`), user `khef`, password `vault_arr_password`.

## 1. Secrets (once)
Add these to the vault (`ansible-vault edit inventories/group_vars/all/vault.yml`; examples in `docs/examples/vault.example.yml`):

| Variable | How to make it |
|---|---|
| `vault_arr_password` | A long password. Used for all four web pages. |
| `vault_sonarr_api_key`, `vault_radarr_api_key`, `vault_prowlarr_api_key` | `openssl rand -hex 16` for each (exactly 32 hex characters). The apps are told their key from the vault, so a restored database can never leave them with a different one. |
| `vault_nordvpn_wireguard_private_key` | Your NordLynx (WireGuard) private key, see below. |

### Get the NordVPN key
NordVPN does not show the WireGuard key in its apps. The way that works with any client:
1. Sign in at my.nordaccount.nordvpn.com > NordVPN > *Manual setup* > *Set up NordVPN manually* > *Generate new token* (an access token, valid 30 days; it is only needed for the next step).
2. From WSL (replace `<TOKEN>`; the token will be in your shell history, so clear it afterwards with `history -c` or revoke it in the same page):
   ```
   curl -s -u token:<TOKEN> https://api.nordvpn.com/v1/users/services/credentials | jq -r .nordlynx_private_key
   ```
3. Put the output (about 44 characters ending in `=`) in the vault as `vault_nordvpn_wireguard_private_key`. The token itself is no longer needed.
Treat the key like a password. If it ever leaks, generate a new token and repeat; the old key stops working.

## 2. Deploy, configure, prove (in this order)
| # | Command | You should see |
|---|---|---|
| 1 | `make arr` | It pre-pulls every image on the workers (a wrong tag stops here, before anything changes), creates the Secrets straight in the cluster, applies the manifests and waits. The downloader pod is "ready" only once Gluetun's tunnel is up. Ends with the four web addresses. |
| 2 | `make arr-provision` | The first run signs qBittorrent in with its one-time password and sets yours, then sets sign-in on Sonarr/Radarr/Prowlarr, qBittorrent's preferences and the `tv` and `movies` categories, the root folders, the download client in both apps, the Sonarr/Radarr links inside Prowlarr, and your indexers. A second run says `changed=0`. |
| 3 | `make arr-vpn-test` | Three `OK` lines: the downloader's public address is not yours, it cannot reach your router, its DNS is the tunnel's own resolver. Read-only. |
| 4 | `make arr-backup-now` | `saved sonarr-... zip`, the same for radarr and prowlarr, then `Done.` |
`make site` and `make rebuild` run steps 1, 2 and the backup job for you when `arr_enabled: true`.

## 3. Indexers (declared in Git)
Prowlarr holds the list of torrent sites and pushes it to Sonarr and Radarr. Which sites you use is your choice; this repo gives you the mechanism.
1. List what Prowlarr knows: `make arr-provision ARGS="-e arr_show_indexer_definitions=true"`
2. List the settings of one: `make arr-provision ARGS="-e arr_show_indexer_fields=<definition>"`
3. Declare it in `inventories/group_vars/all/arr.yml`:
   ```yaml
   arr_prowlarr_indexers:
     - name: Example Tracker          # your label
       definition: examplesite        # one from step 1 (use "Torznab" for a Torznab/Jackett-style URL)
       fields:                        # names from step 2
         username: "{{ vault_example_user }}"
         password: "{{ vault_example_password }}"
       # optional: enable: true, priority: 25, app_profile_id: 1
   ```
   Secrets go in the vault and are referenced like above; the Git file never holds them.
4. `make arr-provision`. Prowlarr tests the indexer first. If the test fails you see the site's own message. To save anyway: `ARGS="-e arr_provision_force_save=true"`.
A typo in a setting name stops with the list of valid names. Prowlarr hides stored passwords, so a changed password in the vault is re-sent with `ARGS="-e arr_provision_force=true"`.

## 4. Backups and restore
- `arr-backup` CronJob, **05:40** every night (after Jellyfin's 05:30): each app makes its own backup zip (database + `config.xml`), the job downloads it to `<hdd>/data/backups/arr/<app>-<date>.zip` and keeps the newest 14 of each.
- `make arr-restore` (type `RESTORE`): stops the three apps, unzips each app's newest zip into its config volume, starts them, then runs `make arr-provision` so Git's settings win over anything old. An app with no zip is left alone.
- `make rebuild` restores them automatically after the Jellyfin restore. Take a backup first: `make arr-backup-now` (also listed in `docs/rebuild.md` section 1).
- A zip also holds the app's old API key, but the apps always take theirs from the vault (environment), so a restore onto a new cluster just works.

## 5. How the kill switch works (and what is not proven)
1. One pod, one network namespace: qBittorrent has no interface except the ones Gluetun controls.
2. Gluetun's firewall drops everything that does not go through the tunnel (only the web port 8080 is reachable from the cluster).
3. DNS inside the pod is `127.0.0.1` (Gluetun's resolver, through the tunnel): the cluster's and the router's DNS are never asked.
4. A NetworkPolicy (second lock, enforced by the cluster) lets the pod send only UDP 51820 to non-private addresses.
5. qBittorrent is not told to bind a "network interface" in its settings; with 1 to 4 it has nothing else to bind to.

`make arr-vpn-test` proves the address, the LAN block and the DNS **while the tunnel is up**. It does not take the tunnel down to watch the downloads stop. If you want to see that once: on kasrkin `kubectl -n downloads exec deploy/qbittorrent -c gluetun -- sh -c 'ip link set tun0 down'` (or wg0; `ip link` shows which), then `kubectl -n downloads exec deploy/qbittorrent -c qbittorrent -- wget -T 5 -qO- http://api.ipify.org` must time out. Gluetun brings the tunnel back by itself; deleting the pod also resets it.

NordVPN offers **no port forwarding**, so qBittorrent can connect out but not be connected to. Downloads work; seeding and some slow swarms are worse than with a forwarded port. If that matters, ProtonVPN or PIA are the usual alternatives (Gluetun supports both; it is a change in `downloads.yaml.j2` and the vault).

## 6. Things to know
- **Prowlarr's own traffic (searches, indexer sites) does not go through the VPN.** Only qBittorrent's does. Indexer sites see your home address; the torrent swarm does not. Routing Prowlarr through Gluetun's HTTP proxy is possible and would be the next step if you want it.
- **Sonarr/Radarr do not tell Jellyfin** a file arrived. Jellyfin finds it at its next scan. In Sonarr/Radarr: Settings > Connect > Add > Jellyfin (Emby) with a Jellyfin API key; not done from Git yet.
- **Between `make arr` and `make arr-provision`** the apps are up with sign-in required but no user yet; the first visitor to the page could create one. Run step 2 straight after step 1 (the pages are LAN-only and `make rebuild` runs both back to back).
- **qBittorrent bans an address for a while after 5 wrong passwords.** Restarting its pod clears it: `kubectl -n downloads rollout restart deploy/qbittorrent`.
- Changing `vault_arr_password` later: the apps and qBittorrent keep the old password until you change it in their pages, or `make arr-provision ARGS="-e arr_provision_force=true"` for Sonarr/Radarr/Prowlarr; for qBittorrent sign in with the old password and change it in Tools > Options > Web UI.
- Updating an app: change the version in `versions.yml`, `make arr`. Sonarr/Radarr/Prowlarr migrate their databases forward on start and cannot go back; the nightly backup is the way back.

## 7. If something does not work
| Symptom | Likely cause and fix |
|---|---|
| `make arr` fails at the image pull | A tag in `versions.yml` does not exist (the message names it). Fix the tag; nothing was changed in the cluster. |
| Gluetun log: "unauthorized" / "authentication failed" | The Nord key is wrong or the token was revoked. Make a new one (section 1). |
| Gluetun log: "operation not permitted" about `/dev/net/tun` or iptables | The container runtime did not allow the device. `make arr ARGS="-e arr_vpn_privileged=true"` (and set `arr_vpn_privileged: true` in `arr.yml` to keep it). |
| Gluetun log: unknown country | `arr_vpn_country` must be a Nord country name Gluetun knows, for example `United States`. |
| Pods of Sonarr/Radarr/Prowlarr stuck in `CrashLoopBackOff` or `Error` right after start | `kubectl -n media logs deploy/sonarr`. The hotio images start as root, fix the config folder's owner, then drop to the media user (uid 1500); a pod-security change that removes the CHOWN/SETUID/SETGID capabilities breaks that. |
| `make arr-provision`: "Unable to connect to qBittorrent" | The qBittorrent pod is not ready (Gluetun still connecting), or a policy blocks media > downloads on 8080. `make cluster-hardening` lists the policies. |
| `make arr-provision`: Prowlarr cannot reach Sonarr | Sonarr is still starting; run it again. |
| Torrents sit at "stalled" | No peers yet, the indexer is dead, or (NordVPN, no forwarded port) a swarm of seeds that only accept incoming connections. |
| Import fails: "no files found" / hardlink error | Sonarr/Radarr and qBittorrent must see the file at the same path (`/data/downloads/...`). Do not change `arr_qbittorrent_categories` paths without changing the mounts. |

## What was and was not tested
Tested against stand-ins: every API call is checked against the real OpenAPI files of Sonarr, Radarr and Prowlarr (a wrong field name fails); first run, second run (`changed=0`), forced re-send, a changed indexer, a typo, a refused indexer, a wrong qBittorrent password; the backup and restore scripts under a real busybox; the rendered manifests and policies as valid YAML; ansible-lint (production profile) and yamllint.
**Not tested (needs the real cluster):** that the hotio images start under the `media` pod-security level, that Gluetun's tunnel comes up with these settings and the tun device on the node, that NordVPN accepts the key, the real indexer protocols. `make arr` is built to fail early and say why (image pull first, then the Gluetun log).
