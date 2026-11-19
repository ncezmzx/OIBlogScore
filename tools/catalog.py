#!/usr/bin/env python3
"""Offline discovery of canonical algorithms, audit notes and pinned source materials."""
import argparse
from collections import Counter
import json
import sys

from catalog_data import RELATIONS, ROOT, build, normalize, read, related, source_view


def load(root=ROOT):
    """Legacy local topic manifest, used by the authoring gate."""
    return read(root / 'index.json')


def search(data, query='', category=None, provider=None, tag=None):
    needle = normalize(query)
    matches = []
    for row in data['algorithms'].values():
        if (category and row['category'] != category) or (tag and tag not in (row['id'], row['category'])):
            continue
        materials = [data['sources'][sid] for sid in row['sources']]
        if provider and not any(s['provider'] == provider for s in materials):
            continue
        names = [normalize(key) for key in (row['id'], row['title'], *row['aliases'])]
        if needle in names:
            rank = 0 if row.get('identity') != 'upstream-candidate' else 1
        elif not needle or any(needle in name for name in names):
            rank = 2
        elif any(needle in normalize(s['title']) for s in materials):
            rank = 3
        else:
            continue
        matches.append((rank, row['id'], row))
    # Canonical exact aliases supersede coincidental subtitle hits.
    exact = [row for rank, _, row in matches if rank == 0]
    return sorted(exact, key=lambda row: row['id']) if exact else [row for _, _, row in sorted(matches)]


def source_search(data, query='', provider=None, tag=None, kind=None, author=None):
    needle = normalize(query)
    for sid, row in sorted(data['sources'].items()):
        if provider and row['provider'] != provider or kind and row['kind'] != kind:
            continue
        if author and not any(normalize(author) in normalize(name) for name in row['authors']):
            continue
        view = source_view(data, sid)
        if tag and tag not in view['tags']:
            continue
        if needle in normalize(' '.join((sid, row['title'], *row['authors'], row.get('scope', '')))):
            yield view


def local_text(path):
    target = (ROOT / path).resolve()
    if ROOT.resolve() not in target.parents:
        raise ValueError('Path leaves catalog')
    return target.read_text(encoding='utf-8')


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


SEARCH_COMMANDS = ('find', 'search-sources')
ITEM_COMMANDS = ('show', 'refs', 'review', 'related', 'source', 'variants')
SUMMARY_COMMANDS = ('stats', 'candidates')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in SEARCH_COMMANDS:
        cmd = subs.add_parser(name)
        cmd.add_argument('query', nargs='?', default='')
        cmd.add_argument('--provider')
        cmd.add_argument('--tag', help='canonical algorithm ID or category')
        cmd.add_argument('--json', action='store_true')
        cmd.add_argument('--limit', type=int, default=25, help='0 to show all')
        cmd.add_argument('--category' if name == 'find' else '--kind')
        if name == 'search-sources':
            cmd.add_argument('--author')
    for name in ITEM_COMMANDS:
        cmd = subs.add_parser(name)
        cmd.add_argument('id')
        if name in ('refs', 'related', 'variants'):
            cmd.add_argument('--json', action='store_true')
        if name == 'refs':
            cmd.add_argument('--relation', choices=sorted(RELATIONS))
        if name == 'source':
            cmd.add_argument('--text', action='store_true')
    subs.add_parser('stats')
    candidates = subs.add_parser('candidates')
    candidates.add_argument('--all', action='store_true', help='include already mapped baseline candidates')
    args = parser.parse_args(argv)
    try:
        data = build()
        command = args.command
        if command in ('find', 'search-sources'):
            if args.provider and args.provider not in data['providers']:
                raise ValueError('Unknown source provider: ' + args.provider)
            if args.tag and args.tag not in set(data['algorithms']) | set(data['categories']):
                raise ValueError('Unknown algorithm ID or category tag: ' + args.tag)
            if args.limit < 0:
                raise ValueError('Limit must be nonnegative')
            if command == 'find':
                if args.category and args.category not in data['categories']:
                    raise ValueError('Unknown category: ' + args.category)
                rows = search(data, args.query, args.category, args.provider, args.tag)
            else:
                rows = list(source_search(data, args.query, args.provider, args.tag, args.kind, args.author))
            rows = rows[:args.limit] if args.limit else rows
            if args.json:
                dump(rows)
            else:
                for row in rows:
                    detail = row['url'] if command == 'search-sources' else row['category'] + ' / ' + row['review']
                    print(f"{row['id']}\t{row['title']}\t{detail}")
            return int(not rows)
        if command in ('stats', 'candidates'):
            cohort = read(ROOT / 'knowledge/triage-baseline.json')['source_ids']
            triage = []
            for sid in cohort:
                view = source_view(data, sid)
                mapped = [a for a in view['associations'] if a['relation'] != 'unclassified']
                triage.append(dict(source=sid, title=view['title'], mapped=mapped))
            if command == 'candidates':
                dump([r for r in triage if args.all or not r['mapped']])
                return 0
            mapped_rows = [r for r in triage if r['mapped']]
            counts = {kind: sum(any(a['relation'] == kind for a in r['mapped']) for r in mapped_rows) for kind in sorted(RELATIONS)}
            counts['unclassified'] = len(cohort) - len(mapped_rows)
            independent = {a['algorithm'] for r in mapped_rows for a in r['mapped'] if a['relation'] in ('exact','alias')}

            dump({'algorithms': dict(Counter(row['category'] for row in data['algorithms'].values())),
                  'triage': dict(total=len(cohort), mapped=len(mapped_rows), pending=counts['unclassified'],
                                 identity_targets=len(independent), by_relation=counts),
                  'by_provider': dict(Counter(row['provider'] for row in data['sources'].values())),
                  'by_mode': dict(Counter(row['mode'] for row in data['sources'].values())),
                  'review': dict(Counter(row['review'] for row in data['algorithms'].values())),
                  'local_artifacts': dict(markdown=sum('path' in r for r in data['algorithms'].values()),
                                          structured=len(data['notes'])),
                  'canonical': sum(not row.get('identity') for row in data['algorithms'].values()),
                  'curated': dict(Counter(row['kind'] for row in data['sources'].values() if 'metadata_status' in row))})
            return 0
        key = args.id
        if command == 'source':
            if key not in data['sources']:
                raise ValueError('Unknown source ID: ' + key)
            row = data['sources'][key]
            dump(source_view(data, key))
            if args.text:
                if row['mode'] != 'verbatim':
                    print('Full text is external; consult the pinned permalink or original URL.', file=sys.stderr)
                    return 1
                print('\n--- Unmodified upstream text; license and attribution above ---\n')
                print(local_text('sources/' + row['text_path']), end='')
            return 0
        if key not in data['algorithms']:
            raise ValueError('Unknown topic ID: ' + key)
        row = data['algorithms'][key]
        if command in ('refs', 'variants'):
            selected = {'variant','implementation'} if command == 'variants' else ({args.relation} if args.relation else RELATIONS)
            refs = [dict(source_view(data, a['source']), relation=a['relation'], rationale=a['basis'])
                    for a in row.get('associations', ()) if a['relation'] in selected]
            if args.json:
                dump(refs)
            else:
                for item in refs:
                    print('{id}\t{title}\t{mode}\t{url}\t{relation}\t{trust}\t{license}'.format(**item))
        elif command == 'related':
            groups = related(data, key)
            if args.json:
                dump(groups)
            else:
                for group, keys in groups.items():
                    for other in keys:
                        print(f"{group}\t{other}\t{data['algorithms'][other]['title']}")
        elif command == 'review' and key in data['notes']:
            dump(data['notes'][key])
        elif 'path' in row:
            print(local_text(row['path']), end='')
        elif command == 'review':
            print('No local review analysis. Use refs, then verify conditions independently.', file=sys.stderr)
            return 1
        else:
            dump(row)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
