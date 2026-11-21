#!/usr/bin/env python3
"""Offline discovery of canonical algorithms, audit notes and pinned source materials."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from catalog_io import local_path, read_text

from catalog_data import RELATIONS, ROOT, build, name_key, normalize, read, related, source_view


def load(root=ROOT):
    """Legacy local topic manifest, used by the authoring gate."""
    return read(local_path(root, 'index.json'))


def search(data, query='', category=None, provider=None, tag=None, exact=False, include_related=False):
    if len(query) > 4096:
        raise ValueError('Search query exceeds 4096 characters')
    needle = name_key(query)
    matches, eligible = [], {}
    for row in data['algorithms'].values():
        if (category and row['category'] != category) or (tag and tag not in (row['id'], row['category'])):
            continue
        materials = [data['sources'][sid] for sid in row['sources']]
        if provider:
            materials = [s for s in materials if s['provider'] == provider]
            if not materials:
                continue
        eligible[row['id']] = row
        fields = [('id', row['id']), *[('alias', a) for a in row['aliases']], ('title', row['title'])]
        hits = []
        if not needle:
            hits.append((8, {'field': 'all', 'value': '', 'match': 'browse'}))
        else:
            for field, text in fields:
                key = name_key(text)
                if (normalize(query) == normalize(text) if field == 'id' else needle == key):
                    hits.append(({'id':0, 'alias':1, 'title':2}[field], {'field':field, 'value':text, 'match':'exact'}))
                elif needle in key:
                    hits.append((3 if field == 'alias' else 4, {'field':field, 'value':text, 'match':'contains'}))
            if needle == name_key(row['category']):
                hits.append((6, {'field':'category', 'value':row['category'], 'match':'filter-match'}))
            for item in materials:
                if needle in name_key(item['title']):
                    relation = next((a['relation'] for a in row.get('associations', ()) if a['source'] == item['id']), 'unclassified')
                    hits.append((5, {'field':'source_title', 'value':item['title'], 'source_id':item['id'],
                                     'match':'contains', 'relation':relation, 'trust':item.get('trust')}))
        if exact:
            hits = [hit for hit in hits if hit[1]['match'] == 'exact']
        if hits:
            hits.sort(key=lambda item: item[0])
            rank = hits[0][0]
            matches.append((rank, row['id'], dict(row, match=hits[0][1], matching_fields=[h[1] for h in hits])))
    exact_ids = {key for rank, key, _ in matches if rank <= 2}
    ambiguous = len(exact_ids) > 1
    if include_related and not exact and exact_ids:
        # Only authored edges, not all shared-source neighbours. Broad
        # tutorials would otherwise promote unrelated entities.
        weak = {}
        for key, note in data.get('notes', {}).items():
            for other in note['related']:
                for src, dst in ((key, other), (other, key)):
                    if src in exact_ids and dst in eligible:
                        weak.setdefault(dst, []).append(dict(field='editorial_relation', value=src, match='related'))
        direct = {key for _, key, _ in matches}
        for key in sorted(weak.keys() - direct):
            hits = sorted(weak[key], key=lambda h: h['value'])
            matches.append((7, key, dict(eligible[key], match=hits[0], matching_fields=hits)))
    notes = data.get('notes', {})
    return [dict(row, ambiguous_exact=ambiguous, has_review=row['id'] in notes,
                 claim_states=sorted({c['status'] for c in notes.get(row['id'], {}).get('claims', ())}))
            for _, _, row in sorted(matches)]


def source_search(data, query='', provider=None, tag=None, kind=None, author=None):
    if len(query) > 4096:
        raise ValueError('Search query exceeds 4096 characters')
    needle = name_key(query)
    matches = []
    for sid, row in data['sources'].items():
        if (provider and row['provider'] != provider) or (kind and row['kind'] != kind):
            continue
        if author and not any(name_key(author) in name_key(name) for name in row['authors']):
            continue
        view = source_view(data, sid)
        if tag and tag not in view['tags']:
            continue
        fields = [('id', sid), ('title', row['title']), ('scope', row.get('scope', '')),
                  *[('author', a) for a in row['authors']]]
        hits = [dict(field=k, value=v, match='exact' if needle == name_key(v) else 'contains')
                for k, v in fields if needle and needle in name_key(v)]
        if hits or not needle:
            def rank(hit):
                return (hit['match'] != 'exact', ('id','title','author','scope').index(hit['field']))
            hits.sort(key=rank)
            matches.append((rank(hits[0]) if hits else (True, 4), sid, dict(view, matching_fields=hits)))
    for _, _, row in sorted(matches):
        yield row


def local_text(path, root=ROOT):
    return read_text(local_path(root, path))


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


SEARCH_COMMANDS = ('find', 'search-sources')
ITEM_COMMANDS = ('show', 'refs', 'review', 'related', 'source', 'variants')
SUMMARY_COMMANDS = ('stats', 'candidates')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Catalog data directory (not the repository root)')
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
        else:
            cmd.add_argument('--exact', action='store_true', help='filter to exact IDs, aliases and titles')
            cmd.add_argument('--include-related', action='store_true', help='append authored neighbours of exact hits')
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
        data = build(args.root)
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
                rows = search(data, args.query, args.category, args.provider, args.tag, args.exact, args.include_related)
            else:
                rows = list(source_search(data, args.query, args.provider, args.tag, args.kind, args.author))
            rows = rows[:args.limit] if args.limit else rows
            if args.json:
                dump(rows)
            else:
                for row in rows:
                    detail = row['url'] if command == 'search-sources' else row['category'] + ' / ' + row['review'] + ' / ' + row['match']['field'] + ':' + row['match']['match']
                    print(f"{row['id']}\t{row['title']}\t{detail}")
            return int(not rows)
        if command in ('stats', 'candidates'):
            cohort = read(local_path(args.root, 'knowledge/triage-baseline.json'))['source_ids']
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
                  'counts': dict(sources=len(data['sources']), providers=len(data['providers']),
                                 upstream_candidates=sum(bool(r.get('identity')) for r in data['algorithms'].values()),
                                 crosswalk_relations=dict(Counter(a['relation'] for r in data['algorithms'].values()
                                                                  if not r.get('identity') for a in r.get('associations', []))),
                                 canonical_with_local_knowledge=sum('path' in r or key in data['notes']
                                                                     for key, r in data['algorithms'].items() if not r.get('identity')),
                                 canonical_with_identity_source=sum(any(a['relation'] in ('exact','alias') for a in r.get('associations', []))
                                                                    for r in data['algorithms'].values() if not r.get('identity')),
                                 claims=sum(len(n.get('claims', [])) for n in data['notes'].values())),
                  'canonical_by_category': dict(Counter(r['category'] for r in data['algorithms'].values() if not r.get('identity'))),
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
                print(local_text('sources/' + row['text_path'], args.root), end='')
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
            print(local_text(row['path'], args.root), end='')
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
