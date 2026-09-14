#!/usr/bin/env python3
import argparse
import concurrent.futures
import csv
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED
from pathlib import Path
from urllib.parse import urlsplit

TARGET_HOST = 'api.ipify.org'
TARGET_PORT = 443
TLS_CONTEXT = ssl.create_default_context()
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return number


def positive_float(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return number


def port_number(value):
    number = int(value)
    if number < 1 or number > 65535:
        raise argparse.ArgumentTypeError('must be between 1 and 65535')
    return number


def normalize_proxy(value):
    value = str(value or '').strip().strip('\ufeff')
    if not value or value.startswith('#'):
        return None
    value = value.split()[0].strip()
    if '://' not in value:
        value = f'socks5://{value}'
    elif value.startswith('http://'):
        value = 'socks5://' + value[len('http://'):]
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != 'socks5' or not parsed.hostname or port is None:
        return None
    if port < 1 or port > 65535:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path or parsed.query or parsed.fragment:
        return None
    host = parsed.hostname
    formatted_host = f'[{host}]' if ':' in host else host
    return f'{formatted_host}:{port}'


def parse_proxy_endpoint(proxy):
    normalized = normalize_proxy(proxy)
    if not normalized:
        raise ValueError(f'invalid proxy: {proxy!r}')
    parsed = urlsplit(f'socks5://{normalized}')
    if not parsed.hostname or parsed.port is None:
        raise ValueError(f'invalid proxy: {proxy!r}')
    return parsed.hostname, parsed.port


def fetch_url(url, timeout):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_SOURCE_BYTES + 1)
    if len(payload) > MAX_SOURCE_BYTES:
        raise ValueError(f'source response exceeds {MAX_SOURCE_BYTES} bytes')
    return payload.decode('utf-8', 'ignore')


def collect_sources(sources_path, output_path, timeout, source_result_path):
    all_proxies = set()
    source_rows = []
    urls = [
        line.strip()
        for line in sources_path.read_text(encoding='utf-8', errors='replace').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_result_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_path, '\n'.join(sorted(all_proxies)) + ('\n' if all_proxies else ''))

    def write_source_results(file):
        writer = csv.DictWriter(file, fieldnames=['url', 'status', 'count', 'seconds', 'error'])
        writer.writeheader()
        writer.writerows(source_rows)

    atomic_write_csv(source_result_path, write_source_results)
    print(f'[collect done] unique={len(all_proxies)} output={output_path}')


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError('unexpected eof')
        data += chunk
    return data


def proxy_connect(proxy, protocol, timeout, target_host, target_port):
    host, port = parse_proxy_endpoint(proxy)
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        if protocol == 'http':
            request = (
                f'CONNECT {target_host}:{target_port} HTTP/1.1\r\n'
                f'Host: {target_host}:{target_port}\r\n'
                'Proxy-Connection: keep-alive\r\n'
                'User-Agent: socks5-filter/1.0\r\n\r\n'
            ).encode('ascii')
            sock.sendall(request)
            status = recv_exact(sock, 12)
            parts = status.split(b' ', 2)
            if len(parts) < 2 or not parts[0].startswith(b'HTTP/') or not parts[1].startswith(b'2'):
                raise OSError(f'http connect failed: {status[:80]!r}')
            while True:
                line = bytearray()
                while not line.endswith(b'\r\n'):
                    chunk = sock.recv(1)
                    if not chunk:
                        raise OSError('unexpected eof in http connect headers')
                    line += chunk
                    if len(line) > 8192:
                        raise OSError('http connect header line too long')
                if line in (b'\r\n',):
                    break
            return sock
        if protocol == 'socks4':
            host_bytes = socket.inet_aton(host)
            request = b'\x04\x01' + target_port.to_bytes(2, 'big') + host_bytes + b'\x00'
            sock.sendall(request)
            header = recv_exact(sock, 8)
            if header[0] != 0 or header[1] not in (0x5A, 0x00):
                raise OSError(f'socks4 connect failed: {header[:2].hex()}')
            return sock
        # socks5
        sock.sendall(b'\x05\x01\x00')
        hello = recv_exact(sock, 2)
        if hello != b'\x05\x00':
            raise OSError(f'socks5 auth failed: {hello.hex()}')
        target = target_host.encode('idna')
        if len(target) > 255:
            raise ValueError('target host is too long for SOCKS5')
        request = b'\x05\x01\x00\x03' + bytes([len(target)]) + target + target_port.to_bytes(2, 'big')
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
    except Exception:
        sock.close()
        raise


def build_http_request(target_host):
    host_header = target_host.encode('idna').decode('ascii')
    return (
        f'GET /?format=text HTTP/1.1\r\n'
        f'Host: {host_header}\r\n'
        'User-Agent: socks5-filter/1.0\r\n'
        'Connection: close\r\n\r\n'
    ).encode('ascii')


def parse_exit_ip(response):
    header, separator, body = response.partition(b'\r\n\r\n')
    if not separator:
        raise OSError('invalid HTTP response')
    status_line = header.split(b'\r\n', 1)[0].decode('ascii', 'ignore')
    match = re.match(r'^HTTP/\d(?:\.\d)?\s+(\d{3})\b', status_line)
    if not match or not 200 <= int(match.group(1)) < 300:
        raise OSError(f'bad HTTP status: {status_line[:80]!r}')
    body_text = body.decode('utf-8', 'ignore').strip().splitlines()[0] if body.strip() else ''
    try:
        return str(ipaddress.ip_address(body_text))
    except ValueError as exc:
        raise OSError(f'bad response: {body_text[:80]!r}') from exc


def check_one(proxy, timeout, target_host, target_port, protocol):
    started = time.perf_counter()
    row = {
        'proxy': proxy,
        'ok': False,
        'latency_ms': '',
        'exit_ip': '',
        'error': '',
    }
    raw_sock = None
    try:
        request = build_http_request(target_host)
        with proxy_connect(proxy, protocol, timeout, target_host, target_port) as raw_sock:
            with TLS_CONTEXT.wrap_socket(raw_sock, server_hostname=target_host) as tls_sock:
                tls_sock.settimeout(timeout)
                tls_sock.sendall(request)
                chunks = []
                total_bytes = 0
                while True:
                    chunk = tls_sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > MAX_RESPONSE_BYTES:
                        raise OSError(f'HTTP response exceeds {MAX_RESPONSE_BYTES} bytes')
        elapsed = int((time.perf_counter() - started) * 1000)
        exit_ip = parse_exit_ip(b''.join(chunks))
        row.update({'ok': True, 'latency_ms': elapsed, 'exit_ip': exit_ip})
    except Exception as exc:
        row['error'] = str(exc).replace('\n', ' ')[:180]
    finally:
        if raw_sock is not None:
            raw_sock.close()
    return row


def iter_check_rows(proxies, workers, timeout, target_host, target_port, protocol):
    proxy_iterator = iter(proxies)
    pending = {}
    max_pending = max(workers * 2, workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for _ in range(max_pending):
            try:
                proxy = next(proxy_iterator)
            except StopIteration:
                break
            pending[executor.submit(check_one, proxy, timeout, target_host, target_port, protocol)] = proxy
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                proxy = pending.pop(future)
                try:
                    yield future.result()
                except Exception as exc:
                    yield {
                        'proxy': proxy,
                        'ok': False,
                        'latency_ms': '',
                        'exit_ip': '',
                        'error': str(exc).replace('\n', ' ')[:180],
                    }
                try:
                    next_proxy = next(proxy_iterator)
                except StopIteration:
                    continue
                pending[executor.submit(check_one, next_proxy, timeout, target_host, target_port, protocol)] = next_proxy


def latency_value(row):
    try:
        return int(row['latency_ms'])
    except (TypeError, ValueError):
        return 10**9


def atomic_write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    output_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as file:
            temp_path = Path(file.name)
            file.write(content)
        os.chmod(temp_path, output_mode)
        os.replace(temp_path, path)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def atomic_write_csv(path, writer_func):
    path.parent.mkdir(parents=True, exist_ok=True)
    output_mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as file:
            temp_path = Path(file.name)
            writer_func(file)
        os.chmod(temp_path, output_mode)
        os.replace(temp_path, path)
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


def check_list(input_path, workers, timeout, limit, fast_ms, output_prefix, target_host, target_port, protocol):
    proxies = []
    seen = set()
    for line in input_path.read_text(encoding='utf-8', errors='replace').splitlines():
        proxy = normalize_proxy(line)
        if proxy and proxy not in seen:
            seen.add(proxy)
            proxies.append(proxy)
    if limit:
        proxies = proxies[:limit]
    print(f'[check start] total={len(proxies)} workers={workers} timeout={timeout}', flush=True)
    rows = []
    done = 0
    ok_count = 0
    for row in iter_check_rows(proxies, workers, timeout, target_host, target_port, protocol):
        rows.append(row)
        done += 1
        if row['ok']:
            ok_count += 1
            print(f"[ok] {row['proxy']} {row['latency_ms']}ms exit={row['exit_ip']}", flush=True)
        if done % 500 == 0:
            print(f'[progress] done={done} ok={ok_count}', flush=True)
    rows.sort(key=lambda item: (not item['ok'], latency_value(item), item['proxy']))
    detail_csv_path = Path(f'{output_prefix}_detail.csv')
    detail_json_path = Path(f'{output_prefix}_detail.json')
    alive_path = Path(f'{output_prefix}_alive.txt')
    fast_path = Path(f'{output_prefix}_fast.txt')

    def write_detail_csv(file):
        writer = csv.DictWriter(file, fieldnames=['proxy', 'ok', 'latency_ms', 'exit_ip', 'error'])
        writer.writeheader()
        writer.writerows(rows)

    atomic_write_csv(detail_csv_path, write_detail_csv)
    atomic_write_text(detail_json_path, json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    alive = [row for row in rows if row['ok']]
    atomic_write_text(alive_path, '\n'.join(row['proxy'] for row in alive) + ('\n' if alive else ''))
    fast = [row for row in alive if latency_value(row) <= fast_ms]
    atomic_write_text(fast_path, '\n'.join(row['proxy'] for row in fast) + ('\n' if fast else ''))
    print(f'[check done] tested={len(rows)} alive={len(alive)} fast={len(fast)} fast_ms={fast_ms}')
    print(f'[outputs] {alive_path} {fast_path} {detail_csv_path} {detail_json_path}')


def main():
    parser = argparse.ArgumentParser(description='Collect and verify public SOCKS5 proxies.')
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--sources', default=None)
    parser.add_argument('--protocol', choices=['socks5', 'socks4', 'http'], default='socks5')
    parser.add_argument('--input', default='socks5_all.txt')
    parser.add_argument('--workers', type=positive_int, default=300)
    parser.add_argument('--timeout', type=positive_float, default=6.0)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--fast-ms', type=positive_int, default=3000)
    parser.add_argument('--target-host', default=TARGET_HOST)
    parser.add_argument('--target-port', type=port_number, default=TARGET_PORT)
    parser.add_argument('--output-prefix', default='socks5')
    parser.add_argument('--source-result', default='sources_result.csv')
    args = parser.parse_args()
    if not args.collect and not args.check:
        args.collect = True
        args.check = True
    if args.sources is None:
        args.sources = f'sources_{args.protocol}.txt'
    if args.input == 'socks5_all.txt' and args.protocol != 'socks5':
        args.input = f'{args.protocol}_all.txt'
    if args.collect:
        collect_sources(Path(args.sources), Path(args.input), args.timeout, Path(args.source_result))
    if args.check:
        if args.limit < 0:
            parser.error('--limit must not be negative')
        check_list(
            Path(args.input),
            args.workers,
            args.timeout,
            args.limit,
            args.fast_ms,
            args.output_prefix,
            args.target_host,
            args.target_port,
            args.protocol,
        )


if __name__ == '__main__':
    main()
