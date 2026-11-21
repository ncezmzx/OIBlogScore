#!/usr/bin/env python3
"""Opt-in HTTP check: distinguish dead URLs from rate limits and network blocks."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

from catalog_data import sources
from catalog_quality import https
from console import utf8_stdio


class Redirected(Exception):
    """A redirect to a host that was not explicitly allowlisted."""

    def __init__(self, url):
        self.url = url


class Redirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not https(newurl) or urlsplit(newurl).hostname not in self.hosts:
            raise Redirected(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe(url, hosts, timeout):
    if not https(url) or urlsplit(url).hostname not in hosts:
        return 'unreachable', 'invalid/unregistered URL'
    opener = build_opener(Redirects(hosts))
    try:
        with opener.open(Request(url, headers={'User-Agent':'OIBlogScore-LinkCheck/1.0', 'Range':'bytes=0-0'}), timeout=timeout) as response:
            return 'ok', str(response.status)
    except Redirected as exc:
        return 'redirected', str(exc.url)
    except HTTPError as exc:
        return ('dead' if exc.code in (404, 410) else 'unreachable'), str(exc.code)
    except (URLError, OSError) as exc:
        return 'unreachable', str(exc)


def main():
    utf8_stdio()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider')
    p.add_argument('--limit', type=int, default=10, help='0 = all; default checks a small sample')
    p.add_argument('--timeout', type=float, default=4)
    p.add_argument('--allow-redirect-host', action='append', default=[],
                   help='host allowed to receive a redirect (repeatable)')
    p.add_argument('--permalinks', action='store_true', help='also probe pinned permalinks')
    args = p.parse_args()
    providers, records = sources()
    if args.provider and args.provider not in providers:
        p.error('unknown provider')
    if args.limit < 0 or args.timeout <= 0:
        p.error('invalid limit or timeout')
    selected = [r for r in records if not args.provider or r['provider'] == args.provider]
    urls = {r['url'] for r in selected}
    if args.permalinks:
        urls |= {r['permalink'] for r in selected if r.get('permalink')}
    urls = sorted(urls)
    if args.limit:
        urls = urls[:args.limit]
    hosts = {urlsplit(row['url']).hostname for row in providers.values()} | set(args.allow_redirect_host)
    if args.permalinks:
        hosts |= {urlsplit(url).hostname for url in urls}
    results = Counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, (state, detail) in zip(urls, pool.map(lambda u: probe(u, hosts, args.timeout), urls)):
            print(f'{state}\t{url}\t{detail}')
            results[state] += 1
    print(dict(results))
    return 1 if results['dead'] else 2 if results['unreachable'] else 0


if __name__ == '__main__':
    sys.exit(main())
