#!/usr/bin/env python3
"""Find algorithm references without reading their bodies or using the network."""
import argparse
import json
from pathlib import Path
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1] / 'resources' / 'algorithm-catalog'


def load(root=ROOT):
    return json.loads((root / 'index.json').read_text(encoding='utf-8'))


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def find(index, query, category=None):
    needle = normalize(query)
    ranked = []
    for topic in index['topics']:
        if category is not None and category != topic['category']:
            continue
        keys = [normalize(v) for v in (topic['id'], topic['title'], *topic['aliases'])]
        if needle and not any(needle in key for key in keys):
            continue
        ranked.append((0 if needle in keys else 1, topic['id'], topic))
    return [item[2] for item in sorted(ranked)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    f = subs.add_parser('find')
    f.add_argument('query', nargs='?', default='')
    f.add_argument('--category')
    f.add_argument('--json', action='store_true')
    s = subs.add_parser('show')
    s.add_argument('id')
    args = parser.parse_args(argv)
    try:
        index = load()
        if args.command == 'show':
            topic = next((t for t in index['topics'] if t['id'] == args.id), None)
            if topic is None:
                raise ValueError('Unknown topic ID: ' + args.id)
            path = (ROOT / topic['path']).resolve()
            if ROOT.resolve() not in path.parents:
                raise ValueError('Topic path leaves catalog')
            print(path.read_text(encoding='utf-8'), end='')
            return 0
        if args.category and args.category not in index['categories']:
            raise ValueError('Unknown category: ' + args.category)
        topics = find(index, args.query, args.category)
        if args.json:
            print(json.dumps(topics, ensure_ascii=False, indent=2))
        else:
            for topic in topics:
                print('{id}\t{title}\tresources/algorithm-catalog/{path}'.format(**topic))
        return int(not topics)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
