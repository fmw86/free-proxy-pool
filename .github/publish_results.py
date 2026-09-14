#!/usr/bin/env python3
"""Publish result files to the repo root via the GitHub Contents API.

Used by CI so parallel jobs never git-push against each other: each file is
PUT individually with the API's own optimistic-concurrency (sha) retry, which
serialises cleanly across jobs. Run from the repo root with GH_TOKEN, PREFIX,
JOB in the environment.
"""
import base64
import json
import os
import sys
import time
import urllib.request

REPO = 'fmw86/socks5-filter'
BRANCH = 'main'
API = f'https://api.github.com/repos/{REPO}/contents'
TOKEN = os.environ['GH_TOKEN']
PREFIX = os.environ['PREFIX']


def api_request(method, path, payload=None, expect=(200, 201)):
    request = urllib.request.Request(
        f'{API}/{path}',
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


def current_sha(path):
    status, payload = api_request('GET', f'{path}?ref={BRANCH}', expect=(200, 404))
    return payload.get('sha') if status == 200 else None


def put_file(path):
    with open(path, 'rb') as file:
        content = base64.b64encode(file.read()).decode('ascii')
    for attempt in range(6):
        sha = current_sha(path)
        status, payload = api_request('PUT', path, {
            'message': f'chore(bot): refresh {os.path.basename(path)} [skip ci]',
            'content': content,
            'sha': sha,
            'branch': BRANCH,
        })
        if status in (200, 201):
            print(f'[publish] {path} ok')
            return True
        # 409 = sha mismatch (another job just wrote it); retry with fresh sha
        print(f'[publish] {path} attempt {attempt + 1} -> {status} {str(payload.get("message"))[:80]}; retrying')
        time.sleep(3 * (attempt + 1))
    return False


def main():
    files = [
        f'{PREFIX}_alive.txt',
        f'{PREFIX}_fast.txt',
        f'{PREFIX}_residential.txt',
        f'{PREFIX}_residential_detail.csv',
        f'{PREFIX}_detail.csv',
        f'{PREFIX}_detail.json',
    ]
    if PREFIX == 'nodes':
        files = [
            'nodes_alive.txt',
            'nodes_residential.txt',
            'nodes_detail.csv',
            'nodes_detail.json',
        ]
    else:
        files.append(f'{PREFIX}_sources_result.csv')

    failures = [name for name in files if os.path.exists(name) and not put_file(name)]
    if failures:
        print(f'::error::failed to publish: {failures}')
        sys.exit(1)
    print(f'[publish] {PREFIX} done')


if __name__ == '__main__':
    main()
