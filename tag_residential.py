#!/usr/bin/env python3
"""Tag alive SOCKS5 proxies by network type via the ip-api.com free batch API.

Reads a check_socks5.py detail JSON, looks up each alive proxy's entry IP,
and writes the non-datacenter (residential / ISP / mobile) candidates as a
plain ip:port list plus a CSV with network details. Free public proxy lists
are almost entirely datacenter IPs; this step surfaces the rare home-broadband
nodes among them. Stdlib only.
"""
import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

API_URL = 'http://ip-api.com/batch?fields=status,country,regionName,city,isp,org,as,mobile,hosting,proxy,query'
BATCH_SIZE = 100
BATCH_INTERVAL_SECONDS = 4.5


def load_alive(detail_json_path):
    rows = []
    with detail_json_path.open(encoding='utf-8') as file:
        for row in json.load(file):
            if row.get('ok'):
                rows.append({'proxy': row['proxy'], 'exit_ip': row.get('exit_ip', '')})
    return rows


def entry_ip(proxy):
    return proxy.rsplit(':', 1)[0].strip('[]')


def lookup(ips):
    results = {}
    unique = sorted(set(ips))
    for start in range(0, len(unique), BATCH_SIZE):
        batch = unique[start:start + BATCH_SIZE]
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(batch).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8', 'ignore'))
        for item in payload:
            if item.get('status') == 'success':
                results[item['query']] = item
        if start + BATCH_SIZE < len(unique):
            time.sleep(BATCH_INTERVAL_SECONDS)
    return results


def main():
    parser = argparse.ArgumentParser(description='Tag alive proxies by network type (ip-api.com).')
    parser.add_argument('--input', default='latest/socks5_detail.json')
    parser.add_argument('--output-prefix', default='latest/socks5')
    args = parser.parse_args()

    alive = load_alive(Path(args.input))
    print(f'[tag start] alive={len(alive)}', flush=True)
    residential_path = Path(f'{args.output_prefix}_residential.txt')
    detail_path = Path(f'{args.output_prefix}_residential_detail.csv')
    if not alive:
        residential_path.write_text('', encoding='utf-8')
        detail_path.write_text('', encoding='utf-8')
        print('[tag done] alive=0 nothing to tag')
        return

    try:
        info = lookup([entry_ip(row['proxy']) for row in alive])
    except Exception as exc:
        print(f'[tag warn] network lookup failed: {exc}; writing empty outputs', flush=True)
        residential_path.write_text('', encoding='utf-8')
        detail_path.write_text('', encoding='utf-8')
        return

    residential = []
    csv_rows = []
    for row in alive:
        ip = entry_ip(row['proxy'])
        item = info.get(ip)
        if not item:
            continue
        csv_rows.append({
            'proxy': row['proxy'],
            'country': item.get('country', ''),
            'region': item.get('regionName', ''),
            'city': item.get('city', ''),
            'isp': item.get('isp', ''),
            'org': item.get('org', ''),
            'asn': item.get('as', ''),
            'mobile': item.get('mobile', ''),
            'hosting': item.get('hosting', ''),
            'known_proxy': item.get('proxy', ''),
            'exit_ip': row['exit_ip'],
        })
        if not item.get('hosting'):
            residential.append(row['proxy'])

    with detail_path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    residential_path.write_text('\n'.join(residential) + ('\n' if residential else ''), encoding='utf-8')
    countries = {}
    for row in csv_rows:
        if row['proxy'] in residential:
            countries[row['country']] = countries.get(row['country'], 0) + 1
    top = ', '.join(f'{name}={count}' for name, count in sorted(countries.items(), key=lambda kv: -kv[1])[:8])
    print(f'[tag done] tagged={len(csv_rows)} residential_candidates={len(residential)} ({top})')


if __name__ == '__main__':
    main()
