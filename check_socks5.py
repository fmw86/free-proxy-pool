#!/usr/bin/env python3
import argparse
import concurrent.futures
import csv
import json
import re
import socket
import ssl
import time
import urllib.request
from pathlib import Path

IP_PORT_RE = re.compile(r'^(?:socks5://)?([A-Za-z0-9_.-]+):(\d{1,5})$')
TARGET_HOST = 'api.ipify.org'
TARGET_PORT = 443
HTTP_REQUEST = b'GET /?format=text HTTP/1.1\r\nHost: api.ipify.org\r\nUser-Agent: socks5-filter/1.0\r\nConnection: close\r\n\r\n'


def normalize_proxy(value):
    value = value.strip().strip('\ufeff')
    if not value or value.startswith('#'):
        return None
    value = value.split()[0].strip()
    match = IP_PORT_RE.match(value)
    if not match:
        return None
    host, port_text = match.groups()
    port = int(port_text)
    if port < 1 or port > 65535:
        return None
    return f'{host}:{port}'


def fetch_url(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', 'ignore')


def collect_sources(sources_path, output_path, timeout, source_result_path):
    all_proxies = set()
    source_rows = []
    urls = [line.strip() for line in sources_path.read_text().splitlines() if line.strip() and not line.startswith('#')]
    for url in urls:
        started = time.perf_counter()
        try:
            text = fetch_url(url, timeout)
            found = set()
            for line in text.splitlines():
                proxy = normalize_proxy(line)
                if proxy:
                    found.add(proxy)
            all_proxies.update(found)
            source_rows.append({'url': url, 'status': 'ok', 'count': len(found), 'seconds': round(time.perf_counter() - started, 3), 'error': ''})
            print(f'[source ok] {len(found):6d} {url}', flush=True)
        except Exception as exc:
            source_rows.append({'url': url, 'status': 'error', 'count': 0, 'seconds': round(time.perf_counter() - started, 3), 'error': str(exc)})
            print(f'[source err] {url} {exc}', flush=True)
    output_path.write_text('\n'.join(sorted(all_proxies)) + ('\n' if all_proxies else ''))
    with source_result_path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['url', 'status', 'count', 'seconds', 'error'])
        writer.writeheader()
        writer.writerows(source_rows)
    print(f'[collect done] unique={len(all_proxies)} output={output_path}')


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError('unexpected eof')
        data += chunk
    return data


def socks5_connect(proxy, timeout):
    host, port_text = proxy.rsplit(':', 1)
    port = int(port_text)
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(b'\x05\x01\x00')
    hello = recv_exact(sock, 2)
    if hello != b'\x05\x00':
        raise OSError(f'socks5 auth failed: {hello.hex()}')
    target = TARGET_HOST.encode('idna')
    request = b'\x05\x01\x00\x03' + bytes([len(target)]) + target + TARGET_PORT.to_bytes(2, 'big')
    sock.sendall(request)
    header = recv_exact(sock, 4)
    if header[0] != 5 or header[1] != 0:
        raise OSError(f'socks5 connect failed: {header.hex()}')
    atyp = header[3]
    if atyp == 1:
        recv_exact(sock, 4)
    elif atyp == 3:
        length = recv_exact(sock, 1)[0]
        recv_exact(sock, length)
    elif atyp == 4:
        recv_exact(sock, 16)
    else:
        raise OSError(f'unknown atyp: {atyp}')
    recv_exact(sock, 2)
    return sock


def check_one(proxy, timeout):
    started = time.perf_counter()
    row = {
        'proxy': proxy,
        'ok': False,
        'latency_ms': '',
        'exit_ip': '',
        'error': '',
    }
    try:
        raw_sock = socks5_connect(proxy, timeout)
        context = ssl.create_default_context()
        with context.wrap_socket(raw_sock, server_hostname=TARGET_HOST) as tls_sock:
            tls_sock.settimeout(timeout)
            tls_sock.sendall(HTTP_REQUEST)
            chunks = []
            while True:
                chunk = tls_sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        elapsed = int((time.perf_counter() - started) * 1000)
        response = b''.join(chunks).decode('utf-8', 'ignore')
        body = response.split('\r\n\r\n', 1)[-1].strip()
        if not re.match(r'^[0-9a-fA-F:.]+$', body):
            raise OSError(f'bad response: {body[:80]!r}')
        row.update({'ok': True, 'latency_ms': elapsed, 'exit_ip': body})
    except Exception as exc:
        row['error'] = str(exc).replace('\n', ' ')[:180]
    return row


def check_list(input_path, workers, timeout, limit, fast_ms, output_prefix):
    proxies = [line.strip() for line in input_path.read_text().splitlines() if normalize_proxy(line)]
    if limit:
        proxies = proxies[:limit]
    print(f'[check start] total={len(proxies)} workers={workers} timeout={timeout}', flush=True)
    rows = []
    done = 0
    ok_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_one, proxy, timeout): proxy for proxy in proxies}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            done += 1
            if row['ok']:
                ok_count += 1
                print(f"[ok] {row['proxy']} {row['latency_ms']}ms exit={row['exit_ip']}", flush=True)
            if done % 500 == 0:
                print(f'[progress] done={done} ok={ok_count}', flush=True)
    rows.sort(key=lambda item: (not item['ok'], int(item['latency_ms']) if item['latency_ms'] != '' else 10**9, item['proxy']))
    detail_csv_path = Path(f'{output_prefix}_detail.csv')
    detail_json_path = Path(f'{output_prefix}_detail.json')
    alive_path = Path(f'{output_prefix}_alive.txt')
    fast_path = Path(f'{output_prefix}_fast.txt')
    with detail_csv_path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['proxy', 'ok', 'latency_ms', 'exit_ip', 'error'])
        writer.writeheader()
        writer.writerows(rows)
    detail_json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    alive = [row for row in rows if row['ok']]
    alive_path.write_text('\n'.join(row['proxy'] for row in alive) + ('\n' if alive else ''))
    fast = [row for row in alive if int(row['latency_ms']) <= fast_ms]
    fast_path.write_text('\n'.join(row['proxy'] for row in fast) + ('\n' if fast else ''))
    print(f'[check done] tested={len(rows)} alive={len(alive)} fast={len(fast)} fast_ms={fast_ms}')
    print(f'[outputs] {alive_path} {fast_path} {detail_csv_path} {detail_json_path}')


def main():
    parser = argparse.ArgumentParser(description='Collect and verify public SOCKS5 proxies.')
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--sources', default='sources.txt')
    parser.add_argument('--input', default='socks5_all.txt')
    parser.add_argument('--workers', type=int, default=300)
    parser.add_argument('--timeout', type=float, default=6.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--fast-ms', type=int, default=3000)
    parser.add_argument('--output-prefix', default='socks5')
    parser.add_argument('--source-result', default='sources_result.csv')
    args = parser.parse_args()
    if not args.collect and not args.check:
        args.collect = True
        args.check = True
    if args.collect:
        collect_sources(Path(args.sources), Path(args.input), args.timeout, Path(args.source_result))
    if args.check:
        check_list(Path(args.input), args.workers, args.timeout, args.limit, args.fast_ms, args.output_prefix)


if __name__ == '__main__':
    main()
