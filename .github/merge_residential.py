#!/usr/bin/env python3
"""Merge per-protocol residential lists into a single residential.txt.

Runs in CI after the per-protocol jobs have published their results: the
checkout already contains the bot-committed *_residential.txt files at repo
root. Dedupes across protocols and publishes the merged list via the Contents
API with sha-based retry. Run from the repo root with GH_TOKEN set.
"""
import base64
import json
import os
import time
import urllib.request

REPO = 'fmw86/free-proxy-pool'
BRANCH = 'main'
PATH = 'residential.txt'
TOKEN = os.environ['GH_TOKEN']
SOURCES = ['socks5_residential.txt', 'http_residential.txt', 'socks4_residential.txt']


def api_request(method, path, payload=None):
    request = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/contents/{path}',
        data=json.dumps(payload).encode('utf-8') if payload is not None else None,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'free-proxy-pool-publisher',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode('utf-8', 'ignore') or '{}')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode('utf-8', 'ignore') or '{}')


def main():
    merged = []
    seen = set()
    for name in SOURCES:
        if not os.path.exists(name):
            print(f'[merge] {name} missing (protocol published nothing); skipped')
            continue
        count = 0
        with open(name, encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if line and line not in seen:
                    seen.add(line)
                    merged.append(line)
                    count += 1
        print(f'[merge] {name}: {count} unique')
    content = '\n'.join(merged) + ('\n' if merged else '')
    print(f'[merge] total unique residential: {len(merged)}')

    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
    for attempt in range(6):
        status, payload = api_request('GET', f'{PATH}?ref={BRANCH}')
        status, payload = api_request('PUT', PATH, {
            'message': 'chore(bot): refresh merged residential list [skip ci]',
            'content': encoded,
            'sha': payload.get('sha') if status == 200 else None,
            'branch': BRANCH,
        })
        if status in (200, 201):
            print('[merge] published residential.txt')
            return
        print(f'[merge] attempt {attempt + 1} -> {status}; retrying')
        time.sleep(3 * (attempt + 1))
    raise SystemExit('::error::failed to publish residential.txt')


if __name__ == '__main__':
    main()
