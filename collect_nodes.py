#!/usr/bin/env python3
"""Aggregate free airport/node subscriptions, TCP-test them, tag residential.

Reads node_subs.txt (one subscription URL per line), downloads each, parses
vmess/vless/trojan/ss/ssr/hy2/hysteria2/tuic URIs, dedupes, TCP-connects each
node server, then tags entry IPs via ip-api.com. Stdlib only; no protocol
handshakes — TCP reachability only, so treat results as candidates.
"""
import argparse
import base64
import concurrent.futures
import csv
import json
import re
import socket
import time
import urllib.request
from pathlib import Path

from tag_residential import entry_ip, lookup

NODE_SCHEME_RE = re.compile(r'^(vmess|vless|trojan|ss|ssr|hy2|hysteria2|tuic)://', re.I)
MAX_SUB_BYTES = 32 * 1024 * 1024


def parse_node_uri(uri):
    """Extract (scheme, host, port) from a node URI, or None."""
    match = re.match(r'^([a-z0-9]+)://', uri, re.I)
    if not match:
        return None
    scheme = match.group(1).lower()
    rest = uri[match.end():]
    if scheme == 'vmess':
        try:
            payload = json.loads(base64.b64decode(rest + '=' * (-len(rest) % 4)).decode('utf-8', 'ignore'))
            host = str(payload.get('add', '')).strip('[]')
            port = int(payload.get('port', 0))
            if host and 0 < port < 65536:
                return scheme, host, port
        except Exception:
            return None
        return None
    # user@host:port?params or host:port (ss base64 forms vary)
    m = re.match(r'^(?:[^/@]*@)?(\[[0-9a-fA-F:]+\]|[0-9a-zA-Z._-]+):(\d{1,5})', rest)
    if not m:
        return None
    host = m.group(1).strip('[]')
    port = int(m.group(2))
    if not host or not (0 < port < 65536):
        return None
    return scheme, host, port


def fetch_subscription(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': 'ClashforWindows/0.20.39'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_SUB_BYTES + 1)
    if len(payload) > MAX_SUB_BYTES:
        raise ValueError(f'subscription exceeds {MAX_SUB_BYTES} bytes')
    text = payload.decode('utf-8', 'ignore')
    stripped = ''.join(text.split())
    if stripped and not NODE_SCHEME_RE.search(text) and re.fullmatch(r'[A-Za-z0-9+/=_-]+', stripped):
        try:
            text = base64.b64decode(stripped + '=' * (-len(stripped) % 4)).decode('utf-8', 'ignore')
        except Exception:
            pass
    return text


def collect(subs_path, output_path, timeout, result_path):
    urls = [
        line.strip()
        for line in subs_path.read_text(encoding='utf-8', errors='replace').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
    nodes = {}
    rows = []
    for url in urls:
        started = time.perf_counter()
        try:
            found = 0
            for line in fetch_subscription(url, timeout).splitlines():
                uri = line.strip()
                if not NODE_SCHEME_RE.match(uri):
                    continue
                parsed = parse_node_uri(uri)
                if not parsed:
                    continue
                scheme, host, port = parsed
                if re.fullmatch(r'[0-9.]+', host) and not is_valid_ipv4(host):
                    continue
                key = (scheme, host.lower(), port)
                if key in nodes:
                    continue
                nodes[key] = uri
                found += 1
            rows.append({'url': url, 'status': 'ok', 'count': found, 'seconds': round(time.perf_counter() - started, 3), 'error': ''})
            print(f'[sub ok] {found:6d} {url}', flush=True)
        except Exception as exc:
            rows.append({'url': url, 'status': 'error', 'count': 0, 'seconds': round(time.perf_counter() - started, 3), 'error': str(exc)[:180]})
            print(f'[sub err] {url} {exc}', flush=True)
    with result_path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['url', 'status', 'count', 'seconds', 'error'])
        writer.writeheader()
        writer.writerows(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(nodes.values()) + ('\n' if nodes else ''), encoding='utf-8')
    print(f'[collect done] unique={len(nodes)} output={output_path}')
    return nodes


def is_valid_ipv4(text):
    parts = text.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def tcp_test(nodes, workers, timeout):
    entries = [{'scheme': s, 'host': h, 'port': p, 'uri': u} for (s, h, p), u in nodes.items()]

    def test(entry):
        started = time.perf_counter()
        try:
            with socket.create_connection((entry['host'], entry['port']), timeout=timeout):
                pass
            return {**entry, 'ok': True, 'latency_ms': int((time.perf_counter() - started) * 1000), 'error': ''}
        except Exception as exc:
            return {**entry, 'ok': False, 'latency_ms': '', 'error': str(exc).replace('\n', ' ')[:120]}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for row in executor.map(test, entries):
            results.append(row)
            if row['ok']:
                print(f"[ok] {row['scheme']}://{row['host']}:{row['port']} {row['latency_ms']}ms", flush=True)
    return results


def tag(results):
    alive = [r for r in results if r['ok']]
    if not alive:
        return results, {}
    try:
        info = lookup([r['host'] for r in alive if re.fullmatch(r'[0-9.]+|[0-9a-fA-F:]+', r['host'])])
    except Exception as exc:
        print(f'[tag warn] lookup failed: {exc}', flush=True)
        return results, {}
    for row in alive:
        item = info.get(row['host'])
        if item:
            row['country'] = item.get('country', '')
            row['isp'] = item.get('isp', '')
            row['asn'] = item.get('as', '')
            row['hosting'] = item.get('hosting', '')
            row['mobile'] = item.get('mobile', '')
    return results, info


def main():
    parser = argparse.ArgumentParser(description='Collect and TCP-test free proxy nodes.')
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--subs', default='node_subs.txt')
    parser.add_argument('--input', default='nodes_all.txt')
    parser.add_argument('--workers', type=int, default=300)
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--output-prefix', default='nodes')
    parser.add_argument('--subs-result', default='nodes_subs_result.csv')
    args = parser.parse_args()
    if not args.collect and not args.check:
        args.collect = True
        args.check = True

    nodes = {}
    if args.collect:
        nodes = collect(Path(args.subs), Path(args.input), 20.0, Path(args.subs_result))
    elif args.check:
        nodes = {}
        for uri in Path(args.input).read_text(encoding='utf-8', errors='replace').splitlines():
            uri = uri.strip()
            if NODE_SCHEME_RE.match(uri):
                parsed = parse_node_uri(uri)
                if parsed:
                    nodes[(parsed[0], parsed[1].lower(), parsed[2])] = uri

    if not args.check:
        return
    print(f'[check start] nodes={len(nodes)} workers={args.workers} timeout={args.timeout}', flush=True)
    results = tcp_test(nodes, args.workers, args.timeout)
    results, _ = tag(results)
    results.sort(key=lambda r: (not r['ok'], r['latency_ms'] if r['ok'] else 10**9, r['host']))

    detail_csv = Path(f'{args.output_prefix}_detail.csv')
    detail_json = Path(f'{args.output_prefix}_detail.json')
    alive_path = Path(f'{args.output_prefix}_alive.txt')
    residential_path = Path(f'{args.output_prefix}_residential.txt')
    fieldnames = ['scheme', 'host', 'port', 'ok', 'latency_ms', 'country', 'isp', 'asn', 'hosting', 'mobile', 'error', 'uri']
    with detail_csv.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    detail_json.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    alive = [r['uri'] for r in results if r['ok']]
    alive_path.write_text('\n'.join(alive) + ('\n' if alive else ''), encoding='utf-8')
    residential = [r['uri'] for r in results if r['ok'] and r.get('hosting') == 'False']
    residential_path.write_text('\n'.join(residential) + ('\n' if residential else ''), encoding='utf-8')
    countries = {}
    for r in results:
        if r['ok'] and r.get('hosting') == 'False':
            countries[r.get('country', '?')] = countries.get(r.get('country', '?'), 0) + 1
    top = ', '.join(f'{k}={v}' for k, v in sorted(countries.items(), key=lambda kv: -kv[1])[:8])
    print(f'[check done] tested={len(results)} alive={len(alive)} residential={len(residential)}')
    if top:
        print(f'[residential by country] {top}')


if __name__ == '__main__':
    main()
