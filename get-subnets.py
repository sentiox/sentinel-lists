#!/usr/bin/python3.10

import ipaddress
import urllib.request
import os
import sys
import json

BGP_TOOLS_URL = 'https://bgp.tools/table.txt'
HEADERS = { 'User-Agent': 'itdog.info - hi@itdog.info' }
AS_FILE = 'AS.lst'
IPv4_DIR = 'Subnets/IPv4'
IPv6_DIR = 'Subnets/IPv6'

# ──────────────────────────────────────────────────────────────────────────────
# SAFETY KNOBS
# ──────────────────────────────────────────────────────────────────────────────
# Minimum line counts considered valid for a fresh download.
# If a fetched list is below this, we assume the upstream is broken
# (returned partial / empty / error page) and KEEP the existing file.
#
# IPv4 and IPv6 are separate because IPv6 BGP prefixes for these services
# are NATURALLY tiny (Twitter: 3, Discord: 1, OVH: 4, etc.) — applying IPv4
# thresholds to IPv6 would falsely reject every fresh good fetch.
MIN_LINES = {
    # filename            v4_min  v6_min
    'meta.lst':         {4: 20,  6: 5},
    'twitter.lst':      {4: 5,   6: 1},
    'hetzner.lst':      {4: 30,  6: 2},
    'ovh.lst':          {4: 200, 6: 1},
    'digitalocean.lst': {4: 50,  6: 5},
    'discord.lst':      {4: 3,   6: 1},
    'telegram.lst':     {4: 3,   6: 1},
    'cloudflare.lst':   {4: 5,   6: 1},
    'cloudfront.lst':   {4: 30,  6: 5},
}
# Refuse to write if the new file shrinks by more than this fraction
# vs the existing file on disk. Catches partial responses that pass MIN_LINES.
MAX_SHRINK_FRACTION = 0.5  # new must be >= 50% of old

# Tracks failures so we can exit non-zero at the end (workflow fails → no commit)
HAD_FAILURE = False

AS_META = ['32934','63293','54115','149642']
AS_TWITTER = ['13414']
AS_HETZNER = ['24940']
AS_OVH = ['16276']
AS_DIGITALOCEAN = ['14061']

META = 'meta.lst'
TWITTER = 'twitter.lst'
TELEGRAM = 'telegram.lst'
CLOUDFLARE = 'cloudflare.lst'
HETZNER = 'hetzner.lst'
OVH = 'ovh.lst'
DIGITALOCEAN = 'digitalocean.lst'
CLOUDFRONT = 'cloudfront.lst'

# From https://iplist.opencck.org/
DISCORD_VOICE_V4='https://iplist.opencck.org/?format=text&data=cidr4&site=discord.gg&site=discord.media'
DISCORD_VOICE_V6='https://iplist.opencck.org/?format=text&data=cidr6&site=discord.gg&site=discord.media'

DISCORD = 'discord.lst'

TELEGRAM_CIDR_URL = 'https://core.telegram.org/resources/cidr.txt'

CLOUDFLARE_V4='https://www.cloudflare.com/ips-v4'
CLOUDFLARE_V6='https://www.cloudflare.com/ips-v6'

AWS_IP_RANGES_URL='https://ip-ranges.amazonaws.com/ip-ranges.json'

subnet_list = []

def subnet_summarization(subnet_list):
    subnets = [ipaddress.ip_network(subnet) for subnet in subnet_list]
    return list(ipaddress.collapse_addresses(subnets))

def process_subnets(subnet_list, target_as):
    ipv4_subnets = []
    ipv6_subnets = []

    for subnet_str, as_number in subnet_list:
        try:
            subnet = ipaddress.ip_network(subnet_str)
            if as_number in target_as:
                if subnet.version == 4:
                    ipv4_subnets.append(subnet_str)
                elif subnet.version == 6:
                    ipv6_subnets.append(subnet_str)
        except ValueError:
            print(f"Invalid subnet: {subnet_str}")
            sys.exit(1)

    ipv4_merged = subnet_summarization(ipv4_subnets)
    ipv6_merged = subnet_summarization(ipv6_subnets)

    return ipv4_merged, ipv6_merged

def download_ready_subnets(url_v4, url_v6):
    """Returns (ipv4, ipv6, ok). ok=False on any error."""
    ipv4_subnets = []
    ipv6_subnets = []
    ok = True

    urls = [(url_v4, 4), (url_v6, 6)]

    for url, version in urls:
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    subnets = response.read().decode('utf-8').splitlines()
                    for subnet_str in subnets:
                        if not subnet_str.strip():
                            continue
                        try:
                            subnet = ipaddress.ip_network(subnet_str)
                            if subnet.version == 4:
                                ipv4_subnets.append(subnet_str)
                            elif subnet.version == 6:
                                ipv6_subnets.append(subnet_str)
                        except ValueError:
                            print(f"Invalid subnet: {subnet_str}")
                            ok = False
                else:
                    print(f"Bad HTTP status {response.status} from {url}")
                    ok = False
        except Exception as e:
            print(f"Query error for {url}: {e}")
            ok = False

    return ipv4_subnets, ipv6_subnets, ok

def download_ready_split_subnets(url):
    """Returns (ipv4, ipv6, ok). ok=False on any error."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                print(f"Bad HTTP status {response.status} from {url}")
                return [], [], False
            subnets = response.read().decode('utf-8').splitlines()
    except Exception as e:
        print(f"Query error for {url}: {e}")
        return [], [], False

    ipv4_subnets = []
    ipv6_subnets = []
    for cidr in subnets:
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                ipv4_subnets.append(cidr)
            elif isinstance(net, ipaddress.IPv6Network):
                ipv6_subnets.append(cidr)
        except ValueError:
            print(f"Invalid subnet from {url}: {cidr}")

    return ipv4_subnets, ipv6_subnets, True

def download_aws_cloudfront_subnets():
    """Returns (ipv4, ipv6, ok). ok=False on any error."""
    ipv4_subnets = []
    ipv6_subnets = []

    req = urllib.request.Request(AWS_IP_RANGES_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                print(f"Bad HTTP status {response.status} from {AWS_IP_RANGES_URL}")
                return [], [], False
            data = json.loads(response.read().decode('utf-8'))

            for prefix in data.get('prefixes', []):
                if prefix.get('service') == 'CLOUDFRONT':
                    ipv4_subnets.append(prefix['ip_prefix'])

            for prefix in data.get('ipv6_prefixes', []):
                if prefix.get('service') == 'CLOUDFRONT':
                    ipv6_subnets.append(prefix['ipv6_prefix'])

    except Exception as e:
        print(f"Error downloading AWS CloudFront ranges: {e}")
        return [], [], False

    return ipv4_subnets, ipv6_subnets, True

def _count_existing_lines(filename):
    if not os.path.exists(filename):
        return 0
    try:
        with open(filename, 'r') as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0

def write_subnets_to_file(subnets, filename, fetch_ok=True):
    """
    Safe write: refuse to overwrite if data looks broken.

    Skip write (and mark failure) if any of these are true:
      - fetch_ok=False (upstream errored or partial)
      - subnets is empty
      - subnets has fewer than MIN_LINES.get(basename) entries
      - existing file is bigger and new shrinks by > MAX_SHRINK_FRACTION

    On skip, the existing file is left intact and the script will exit
    non-zero at the end so the GitHub workflow does NOT commit garbage.
    """
    global HAD_FAILURE
    base = os.path.basename(filename)

    # Detect IPv4 vs IPv6 from path so we apply the right threshold.
    if os.sep + 'IPv6' + os.sep in filename or '/IPv6/' in filename:
        version = 6
    else:
        version = 4

    new_count = len(subnets)
    old_count = _count_existing_lines(filename)
    thresholds = MIN_LINES.get(base, {})
    min_required = thresholds.get(version, 1)

    if not fetch_ok:
        print(f"[SKIP] {filename}: upstream fetch failed, keeping existing {old_count} lines")
        HAD_FAILURE = True
        return

    if new_count == 0:
        print(f"[SKIP] {filename}: empty result, keeping existing {old_count} lines")
        HAD_FAILURE = True
        return

    if new_count < min_required:
        print(f"[SKIP] {filename}: only {new_count} entries (< MIN_LINES={min_required}), "
              f"keeping existing {old_count} lines")
        HAD_FAILURE = True
        return

    if old_count > 0 and new_count < old_count * MAX_SHRINK_FRACTION:
        print(f"[SKIP] {filename}: shrunk from {old_count} to {new_count} "
              f"(> {int((1-MAX_SHRINK_FRACTION)*100)}% drop), keeping existing")
        HAD_FAILURE = True
        return

    with open(filename, 'w') as file:
        for subnet in subnets:
            file.write(f'{subnet}\n')
    delta = new_count - old_count
    sign = '+' if delta >= 0 else ''
    print(f"[OK]   {filename}: {new_count} lines ({sign}{delta} vs old)")

def fetch_bgp_table():
    """Returns (subnet_list, ok). subnet_list is empty + ok=False on error."""
    global subnet_list
    try:
        request = urllib.request.Request(BGP_TOOLS_URL, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=60) as response:
            for line in response:
                decoded_line = line.decode('utf-8').strip()
                parts = decoded_line.split()
                if len(parts) != 2:
                    continue
                subnet, as_number = parts
                subnet_list.append((subnet, as_number))
    except Exception as e:
        print(f"FATAL: failed to fetch {BGP_TOOLS_URL}: {e}")
        return False
    if len(subnet_list) < 100000:
        print(f"FATAL: bgp.tools returned only {len(subnet_list)} rows, expected ~900K")
        return False
    print(f"[OK]   bgp.tools: {len(subnet_list)} rows fetched")
    return True

if __name__ == '__main__':
    bgp_ok = fetch_bgp_table()

    # Meta
    if bgp_ok:
        ipv4_merged_meta, ipv6_merged_meta = process_subnets(subnet_list, AS_META)
        write_subnets_to_file(ipv4_merged_meta, f'{IPv4_DIR}/{META}')
        write_subnets_to_file(ipv6_merged_meta, f'{IPv6_DIR}/{META}')
    else:
        write_subnets_to_file([], f'{IPv4_DIR}/{META}', fetch_ok=False)
        write_subnets_to_file([], f'{IPv6_DIR}/{META}', fetch_ok=False)

    # Twitter
    if bgp_ok:
        ipv4_merged_twitter, ipv6_merged_twitter = process_subnets(subnet_list, AS_TWITTER)
        write_subnets_to_file(ipv4_merged_twitter, f'{IPv4_DIR}/{TWITTER}')
        write_subnets_to_file(ipv6_merged_twitter, f'{IPv6_DIR}/{TWITTER}')
    else:
        write_subnets_to_file([], f'{IPv4_DIR}/{TWITTER}', fetch_ok=False)
        write_subnets_to_file([], f'{IPv6_DIR}/{TWITTER}', fetch_ok=False)

    # Hetzner
    if bgp_ok:
        ipv4_merged_hetzner, ipv6_merged_hetzner = process_subnets(subnet_list, AS_HETZNER)
        write_subnets_to_file(ipv4_merged_hetzner, f'{IPv4_DIR}/{HETZNER}')
        write_subnets_to_file(ipv6_merged_hetzner, f'{IPv6_DIR}/{HETZNER}')
    else:
        write_subnets_to_file([], f'{IPv4_DIR}/{HETZNER}', fetch_ok=False)
        write_subnets_to_file([], f'{IPv6_DIR}/{HETZNER}', fetch_ok=False)

    # OVH
    if bgp_ok:
        ipv4_merged_ovh, ipv6_merged_ovh = process_subnets(subnet_list, AS_OVH)
        write_subnets_to_file(ipv4_merged_ovh, f'{IPv4_DIR}/{OVH}')
        write_subnets_to_file(ipv6_merged_ovh, f'{IPv6_DIR}/{OVH}')
    else:
        write_subnets_to_file([], f'{IPv4_DIR}/{OVH}', fetch_ok=False)
        write_subnets_to_file([], f'{IPv6_DIR}/{OVH}', fetch_ok=False)

    # Digital Ocean
    if bgp_ok:
        ipv4_merged_digitalocean, ipv6_merged_digitalocean = process_subnets(subnet_list, AS_DIGITALOCEAN)
        write_subnets_to_file(ipv4_merged_digitalocean, f'{IPv4_DIR}/{DIGITALOCEAN}')
        write_subnets_to_file(ipv6_merged_digitalocean, f'{IPv6_DIR}/{DIGITALOCEAN}')
    else:
        write_subnets_to_file([], f'{IPv4_DIR}/{DIGITALOCEAN}', fetch_ok=False)
        write_subnets_to_file([], f'{IPv6_DIR}/{DIGITALOCEAN}', fetch_ok=False)

    # Discord voice
    ipv4_discord, ipv6_discord, ok = download_ready_subnets(DISCORD_VOICE_V4, DISCORD_VOICE_V6)
    write_subnets_to_file(ipv4_discord, f'{IPv4_DIR}/{DISCORD}', fetch_ok=ok)
    write_subnets_to_file(ipv6_discord, f'{IPv6_DIR}/{DISCORD}', fetch_ok=ok)

    # Telegram
    ipv4_telegram, ipv6_telegram, ok = download_ready_split_subnets(TELEGRAM_CIDR_URL)
    write_subnets_to_file(ipv4_telegram, f'{IPv4_DIR}/{TELEGRAM}', fetch_ok=ok)
    write_subnets_to_file(ipv6_telegram, f'{IPv6_DIR}/{TELEGRAM}', fetch_ok=ok)

    # Cloudflare
    ipv4_cloudflare, ipv6_cloudflare, ok = download_ready_subnets(CLOUDFLARE_V4, CLOUDFLARE_V6)
    write_subnets_to_file(ipv4_cloudflare, f'{IPv4_DIR}/{CLOUDFLARE}', fetch_ok=ok)
    write_subnets_to_file(ipv6_cloudflare, f'{IPv6_DIR}/{CLOUDFLARE}', fetch_ok=ok)

    # AWS CloudFront
    ipv4_cloudfront, ipv6_cloudfront, ok = download_aws_cloudfront_subnets()
    write_subnets_to_file(ipv4_cloudfront, f'{IPv4_DIR}/{CLOUDFRONT}', fetch_ok=ok)
    write_subnets_to_file(ipv6_cloudfront, f'{IPv6_DIR}/{CLOUDFRONT}', fetch_ok=ok)

    # Note: Discord.lst / Meta.lst / Twitter.lst (capitalized) duplicates have
    # been retired. They created two-files-with-same-content collisions on
    # case-insensitive filesystems (Windows/macOS) and confused mihomo about
    # which list to fetch. Consumers should use lowercase URLs only.

    if HAD_FAILURE:
        print("FAIL: at least one list was kept stale due to upstream errors")
        sys.exit(1)
    print("All subnet lists updated successfully")
