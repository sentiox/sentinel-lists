#!/usr/bin/env python3

import ipaddress
import urllib.request
import os
import shutil
import json
import time

RIPE_STAT_URL = 'https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{}'
USER_AGENT = 'sentinel-lists/1.0'
REQUEST_TIMEOUT = 15
REQUEST_RETRIES = 3
IPv4_DIR = 'Subnets/IPv4'
IPv6_DIR = 'Subnets/IPv6'

ASN_SERVICES = {
    'meta.lst': ['32934', '63293', '54115', '149642'],
    'twitter.lst': ['13414'],
    'hetzner.lst': ['24940'],
    'ovh.lst': ['16276'],
    'digitalocean.lst': ['14061'],
}

ASN_TELEGRAM = ['44907', '59930', '62014', '62041', '211157']
TELEGRAM = 'telegram.lst'
# Stable Telegram DC/media ranges. These remain as fallbacks if an upstream
# ASN or CIDR endpoint temporarily returns an incomplete response.
TELEGRAM_V4 = [
    '5.28.192.0/18',
    '91.105.192.0/23',
    '91.108.4.0/22',
    '91.108.8.0/21',
    '91.108.16.0/21',
    '91.108.56.0/22',
    '95.161.64.0/20',
    '149.154.160.0/20',
    '185.76.151.0/24',
]

CLOUDFLARE = 'cloudflare.lst'
CLOUDFRONT = 'cloudfront.lst'

# From https://iplist.opencck.org/
DISCORD_VOICE_V4='https://iplist.opencck.org/?format=text&data=cidr4&site=discord.gg&site=discord.media'
DISCORD_VOICE_V6='https://iplist.opencck.org/?format=text&data=cidr6&site=discord.gg&site=discord.media'

DISCORD = 'discord.lst'

# Discord voice relays are supplied to clients as direct IP addresses. Keep
# known Discord, Google Cloud, i3D.net and Cloudflare relay ranges even when
# the dynamic endpoint misses a region.
DISCORD_VOICE_FALLBACK_V4 = [
    '5.200.14.128/25',
    '34.0.0.0/15',
    '34.2.0.0/15',
    '35.192.0.0/12',
    '35.208.0.0/12',
    '66.22.192.0/18',
    '104.16.0.0/12',
    '138.128.136.0/21',
    '162.158.0.0/15',
    '172.64.0.0/12',
    '192.34.96.0/22',
]

TELEGRAM_CIDR_URL = 'https://core.telegram.org/resources/cidr.txt'

CLOUDFLARE_V4='https://www.cloudflare.com/ips-v4'
CLOUDFLARE_V6='https://www.cloudflare.com/ips-v6'

# https://support.google.com/a/answer/1279090
GOOGLE_MEET = 'google_meet.lst'
GOOGLE_MEET_V4 = [
    '74.125.247.128/32',
    '74.125.250.0/24',
    '142.250.82.0/24',
]
GOOGLE_MEET_V6 = [
    '2001:4860:4864:4:8000::/128',
    '2001:4860:4864:5::/64',
    '2001:4860:4864:6::/64',
]

AWS_CIDR_URL='https://ip-ranges.amazonaws.com/ip-ranges.json'

def make_request(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', USER_AGENT)
    return req

def read_existing_subnets(filename):
    if not os.path.exists(filename):
        return []

    with open(filename, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def open_request(req):
    last_error = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except Exception as error:
            last_error = error
            print(f'Attempt {attempt}/{REQUEST_RETRIES} failed for {req.full_url}: {error}')
            if attempt < REQUEST_RETRIES:
                time.sleep(attempt)

    print(f'Warning: keeping existing data because {req.full_url} is unavailable: {last_error}')
    return None

def subnet_summarization(subnet_list):
    subnets = [ipaddress.ip_network(subnet, strict=False) for subnet in subnet_list]
    return list(ipaddress.collapse_addresses(subnets))

def fetch_asn_prefixes(asn_list):
    ipv4_subnets = []
    ipv6_subnets = []
    complete = True

    for asn in asn_list:
        url = RIPE_STAT_URL.format(asn)
        payload = open_request(make_request(url))
        if payload is None:
            complete = False
            continue

        try:
            data = json.loads(payload.decode('utf-8'))
            prefixes = data['data']['prefixes']
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            print(f'Warning: invalid RIPE response for AS{asn}: {error}')
            complete = False
            continue

        for entry in prefixes:
            prefix = entry.get('prefix')
            try:
                network = ipaddress.ip_network(prefix)
                if network.version == 4:
                    ipv4_subnets.append(prefix)
                else:
                    ipv6_subnets.append(prefix)
            except (ValueError, TypeError):
                print(f'Warning: ignored invalid subnet from AS{asn}: {prefix}')
                complete = False

    return ipv4_subnets, ipv6_subnets, complete

def download_subnets(*urls):
    ipv4_subnets = []
    ipv6_subnets = []
    complete = True

    for url in urls:
        payload = open_request(make_request(url))
        if payload is None:
            complete = False
            continue

        try:
            subnets = payload.decode('utf-8').splitlines()
        except UnicodeDecodeError as error:
            print(f'Warning: invalid response from {url}: {error}')
            complete = False
            continue

        for subnet_str in subnets:
            subnet_str = subnet_str.strip()
            if not subnet_str:
                continue
            try:
                network = ipaddress.ip_network(subnet_str, strict=False)
                if network.version == 4:
                    ipv4_subnets.append(subnet_str)
                else:
                    ipv6_subnets.append(subnet_str)
            except ValueError:
                print(f'Warning: ignored invalid subnet from {url}: {subnet_str}')
                complete = False

    return ipv4_subnets, ipv6_subnets, complete

def download_aws_cloudfront_subnets():
    ipv4_subnets = []
    ipv6_subnets = []

    payload = open_request(make_request(AWS_CIDR_URL))
    if payload is None:
        return ipv4_subnets, ipv6_subnets, False

    try:
        data = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f'Warning: invalid AWS CloudFront response: {error}')
        return ipv4_subnets, ipv6_subnets, False

    for prefix in data.get('prefixes', []):
        if prefix.get('service') == 'CLOUDFRONT':
            ipv4_subnets.append(prefix['ip_prefix'])

    for prefix in data.get('ipv6_prefixes', []):
        if prefix.get('service') == 'CLOUDFRONT':
            ipv6_subnets.append(prefix['ipv6_prefix'])

    return ipv4_subnets, ipv6_subnets, True

def write_subnets_to_file(subnets, filename):
    with open(filename, 'w') as file:
        for subnet in subnets:
            file.write(f'{subnet}\n')

def preserve_existing_on_failure(subnets, filename, complete):
    if complete:
        return subnets

    existing = read_existing_subnets(filename)
    print(f'Preserving {len(existing)} existing entries from {filename}')
    return subnets + existing

def copy_file_legacy(src_filename):
    base_filename = os.path.basename(src_filename)
    new_filename = base_filename.capitalize()
    destination = os.path.join(os.path.dirname(src_filename), new_filename)

    try:
        if os.path.exists(destination) and os.path.samefile(src_filename, destination):
            return
    except OSError:
        pass

    shutil.copy(src_filename, destination)

if __name__ == '__main__':
    # Services from ASN (meta, twitter, hetzner, ovh, digitalocean)
    for filename, asn_list in ASN_SERVICES.items():
        print(f'Fetching {filename}...')
        ipv4, ipv6, complete = fetch_asn_prefixes(asn_list)
        ipv4 = preserve_existing_on_failure(ipv4, f'{IPv4_DIR}/{filename}', complete)
        ipv6 = preserve_existing_on_failure(ipv6, f'{IPv6_DIR}/{filename}', complete)
        write_subnets_to_file(subnet_summarization(ipv4), f'{IPv4_DIR}/{filename}')
        write_subnets_to_file(subnet_summarization(ipv6), f'{IPv6_DIR}/{filename}')

    # Discord voice
    print(f'Fetching {DISCORD}...')
    ipv4_discord, ipv6_discord, complete = download_subnets(DISCORD_VOICE_V4, DISCORD_VOICE_V6)
    ipv4_discord = preserve_existing_on_failure(
        ipv4_discord, f'{IPv4_DIR}/{DISCORD}', complete
    )
    ipv6_discord = preserve_existing_on_failure(
        ipv6_discord, f'{IPv6_DIR}/{DISCORD}', complete
    )
    ipv4_discord = subnet_summarization(
        ipv4_discord + DISCORD_VOICE_FALLBACK_V4
    )
    write_subnets_to_file(ipv4_discord, f'{IPv4_DIR}/{DISCORD}')
    write_subnets_to_file(subnet_summarization(ipv6_discord), f'{IPv6_DIR}/{DISCORD}')

    # Telegram
    print(f'Fetching {TELEGRAM}...')
    ipv4_telegram_file, ipv6_telegram_file, file_complete = download_subnets(
        TELEGRAM_CIDR_URL
    )
    ipv4_telegram_asn, ipv6_telegram_asn, asn_complete = fetch_asn_prefixes(
        ASN_TELEGRAM
    )
    complete = file_complete and asn_complete
    ipv4_telegram_file = preserve_existing_on_failure(
        ipv4_telegram_file, f'{IPv4_DIR}/{TELEGRAM}', complete
    )
    ipv6_telegram_file = preserve_existing_on_failure(
        ipv6_telegram_file, f'{IPv6_DIR}/{TELEGRAM}', complete
    )
    ipv4_telegram = subnet_summarization(ipv4_telegram_file + ipv4_telegram_asn + TELEGRAM_V4)
    ipv6_telegram = subnet_summarization(ipv6_telegram_file + ipv6_telegram_asn)
    write_subnets_to_file(ipv4_telegram, f'{IPv4_DIR}/{TELEGRAM}')
    write_subnets_to_file(ipv6_telegram, f'{IPv6_DIR}/{TELEGRAM}')

    # Cloudflare
    print(f'Fetching {CLOUDFLARE}...')
    ipv4_cloudflare, ipv6_cloudflare, complete = download_subnets(
        CLOUDFLARE_V4, CLOUDFLARE_V6
    )
    ipv4_cloudflare = preserve_existing_on_failure(
        ipv4_cloudflare, f'{IPv4_DIR}/{CLOUDFLARE}', complete
    )
    ipv6_cloudflare = preserve_existing_on_failure(
        ipv6_cloudflare, f'{IPv6_DIR}/{CLOUDFLARE}', complete
    )
    write_subnets_to_file(ipv4_cloudflare, f'{IPv4_DIR}/{CLOUDFLARE}')
    write_subnets_to_file(ipv6_cloudflare, f'{IPv6_DIR}/{CLOUDFLARE}')

    # Google Meet
    print(f'Writing {GOOGLE_MEET}...')
    write_subnets_to_file(GOOGLE_MEET_V4, f'{IPv4_DIR}/{GOOGLE_MEET}')
    write_subnets_to_file(GOOGLE_MEET_V6, f'{IPv6_DIR}/{GOOGLE_MEET}')

    # AWS CloudFront
    print(f'Fetching {CLOUDFRONT}...')
    ipv4_cloudfront, ipv6_cloudfront, complete = download_aws_cloudfront_subnets()
    ipv4_cloudfront = preserve_existing_on_failure(
        ipv4_cloudfront, f'{IPv4_DIR}/{CLOUDFRONT}', complete
    )
    ipv6_cloudfront = preserve_existing_on_failure(
        ipv6_cloudfront, f'{IPv6_DIR}/{CLOUDFRONT}', complete
    )
    write_subnets_to_file(ipv4_cloudfront, f'{IPv4_DIR}/{CLOUDFRONT}')
    write_subnets_to_file(ipv6_cloudfront, f'{IPv6_DIR}/{CLOUDFRONT}')

    # Legacy copies with capitalized names (e.g. meta.lst -> Meta.lst)
    LEGACY_FILES = ['meta.lst', 'twitter.lst', 'discord.lst']
    for legacy_file in LEGACY_FILES:
        copy_file_legacy(f'{IPv4_DIR}/{legacy_file}')
        copy_file_legacy(f'{IPv6_DIR}/{legacy_file}')
