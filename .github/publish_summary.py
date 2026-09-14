#!/usr/bin/env python3
"""Merge this job's summary fragment into updated_at.txt via the Contents API.

Reads summary_fragment.txt (key=value lines produced by the workflow), merges
into the existing updated_at.txt by replacing keys, and PUTs it back with
sha-based retry so parallel jobs don't clobber each other's lines. Run from
the repo root with GH_TOKEN in the environment.
"""
import base64
import json
import os
import time
import urllib.request

REPO = 'fmw86/socks5-filter'
BRANCH = 'main'
PATH = 'updated_at.txt'
TOKEN = os.environ['GH_TOKEN']


def api_request(method, path, payload=None):
    request = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/contents/{path}',
        data=json.dumps(payload).encode('utf-8') if payload is not None else None,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'socks5-filter-publisher',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode('utf-8', 'ignore') or '{}')
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode('utf-8', 'ignore') or '{}')


def main():
    fragment = {}
    with open('summary_fragment.txt', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if '=' in line:
                key, value = line.split('=', 1)
                fragment[key] = value

    for attempt in range(6):
        status, payload = api_request('GET', f'{PATH}?ref={BRANCH}')
        existing = {}
        if status == 200:
            raw = base64.b64decode(payload['content']).decode('utf-8', 'ignore')
            for line in raw.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    existing[key] = value
        existing.update(fragment)
        content = '\n'.join(f'{key}={value}' for key, value in sorted(existing.items())) + '\n'
        status, payload = api_request('PUT', PATH, {
            'message': 'chore(bot): update summary [skip ci]',
            'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
            'sha': payload.get('sha') if status == 200 else None,
            'branch': BRANCH,
        })
        if status in (200, 201):
            print('[summary] updated')
            print(content)
            return
        print(f'[summary] attempt {attempt + 1} -> {status}; retrying')
        time.sleep(3 * (attempt + 1))
    raise SystemExit('::error::failed to update summary')


if __name__ == '__main__':
    main()
