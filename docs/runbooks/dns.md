# Names on the LAN: the DNS server on castellan (`make dns`)

The router (Google Fiber) cannot hold your own names, so castellan runs a small DNS server (dnsmasq). It answers three kinds of question:

| Question | Answer |
|---|---|
| `castellan.home.lan`, `kasrkin.home.lan`, `wyvern.home.lan`, `basilisk.home.lan` | that machine's address (taken from the inventory) |
| anything else ending in `.home.lan` (`jellyfin.home.lan`, a future `seerr.home.lan`, ...) | `ingress_vip` (192.168.1.200), where the ingress sends it to the right app |
| everything else (`youtube.com`, ...) | forwarded to `lan_dns_servers` (the router, then Google) and passed back |

It lives on castellan on purpose: it keeps running while the VMs are destroyed and rebuilt, so a rebuild drill never takes the house's DNS down.
Adding a new app later needs no DNS change, because the wildcard already covers its name.

## Set it up
1. `make dns`. *You should see:* three checks pass at the end (the ingress name, a machine name and an outside name). The play stops with the reason if any fails.
2. In the Google Fiber app, set the network's DNS servers: **first** `192.168.1.50`. The menu is under the network's advanced settings (the wording changes between app versions).
   A second entry is optional, see "A second server" below.
3. Devices pick up the new setting when they renew their lease or reconnect. To force it, turn Wi-Fi off and on, or on Windows run `ipconfig /renew` and `ipconfig /flushdns`.
4. On a device: `nslookup jellyfin.home.lan` should answer `192.168.1.200`, and `http://jellyfin.home.lan` should open Jellyfin.

## Change something
- A fixed name for another device: add it to `dns_server_extra_records` (for example `[{ name: printer.home.lan, ip: 192.168.1.60 }]`) and run `make dns`.
- Different forwarders: change `lan_dns_servers` in `inventories/group_vars/all/main.yml`. The VMs use the same list, so this also changes what they get on their next `make vms`.
- The domain or the ingress address: `lan_domain` and `ingress_vip` in the same file.

## A second server
Routers hand out the DNS servers as a list, but devices do not treat it as strict "first, then second". Many send some questions to the second one, or switch to it after a slow answer.
A second server that knows nothing about `home.lan` (the router, Google, Cloudflare) answers "no such name" for `jellyfin.home.lan`, and the device may cache that for a while. Result: Jellyfin opens most of the time, and sometimes does not.
- Simplest and most predictable: list only castellan. If castellan is off, the internet is unavailable too, which is easy to notice and to fix.
- If you want a fallback anyway, the safe one is a **second copy of this same DNS server on another always-on machine**, not a public resolver. Tell me and I will make the role run on more than one host.

## If a device does not resolve it
- `nslookup jellyfin.home.lan 192.168.1.50` from that device. If this works but a plain `nslookup jellyfin.home.lan` does not, the device is not using castellan: it has not renewed its lease, or it has a fixed DNS setting.
- Browsers with "Secure DNS" / "DNS over HTTPS" switched on (Chrome, Edge, Firefox) skip the LAN's DNS entirely. Turn it off for local names, or use the browser's custom-server option.
- IPv6: if the router also advertises itself as an IPv6 DNS server, a device may ask it instead. Set the DNS servers for IPv6 in the same place in the app if it offers it.
- On castellan: `systemctl status dnsmasq`, `journalctl -u dnsmasq -n 30`, and `dig +short @192.168.1.50 jellyfin.home.lan`.

## Notes
- dnsmasq listens only on 192.168.1.50 (the LAN), never on the internet side. Do not forward port 53 from the router.
- `no-hosts` and `no-resolv` are set, so the Proxmox host's own `/etc/hosts` and resolver settings are not mixed in. castellan itself keeps using whatever it used before.
- IPv6 questions for `home.lan` names get an empty answer ("no IPv6 address"), so devices use the IPv4 one.
