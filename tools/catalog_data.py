"""Pure catalog composition: upstream facts are not accepted audit conclusions."""
from pathlib import Path
import unicodedata
import re

from catalog_io import local_path, read, unique_rows

ROOT = Path(__file__).resolve().parents[1] / 'resources' / 'algorithm-catalog'


RELATIONS = frozenset({'exact', 'alias', 'implementation', 'variant', 'related', 'unclassified'})


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def name_key(text):
    return ' '.join(''.join(' ' if unicodedata.category(c) == 'Pd' else c for c in normalize(text)).split())


def sources(root=ROOT):
    directory = root / 'sources'
    providers = read(local_path(root, 'sources/providers.json'))
    auxiliary = {'providers','import-policy','approved-verbatim','verbatim-pin'}
    expected = {key for key, profile in providers.items() if profile.get('repository')} | {'curated'}
    actual = {path.stem for path in directory.glob('*.json')} - auxiliary
    if actual != expected:
        raise ValueError('Missing or unrecognized source files: ' + ', '.join(sorted(actual ^ expected)))
    records = []
    for name in sorted(expected):
        rows = read(local_path(root, 'sources/' + name + '.json'))
        if not isinstance(rows, list):
            raise ValueError(name + ': expected a source array')
        if name != 'curated' and any(not isinstance(r, dict) or r.get('provider') != name for r in rows):
            raise ValueError(name + ': wrong provider in snapshot')
        records.extend(rows)
    unique_rows(records, "Sources")
    return providers, records


EXTRA = {'geometry': '计算几何', 'foundations': '基础算法、贪心与构造', 'search': '搜索与剪枝',
         'randomized': '随机化', 'techniques': '交互与实战技巧'}
OI_CATEGORIES = dict(basic='foundations', contest='techniques', dp='dp', ds='data-structures',
                     geometry='geometry', graph='graph', lang='techniques', math='mathematics',
                     misc='techniques', search='search', string='strings', topic='techniques')
CP_CATEGORIES = dict(algebra='mathematics', combinatorics='mathematics', data_structures='data-structures',
                     dynamic_programming='dp', game_theory='mathematics', geometry='geometry', graph='graph',
                     linear_algebra='mathematics', num_methods='foundations', others='techniques',
                     schedules='foundations', sequences='foundations', string='strings')


PROVIDER_CATEGORIES = {
    'oi-wiki': OI_CATEGORIES, 'cp-algorithms': CP_CATEGORIES,
    'library-checker': {'data_structure':'data-structures', 'tree':'graph', 'string':'strings', 'geo':'geometry',
                        'graph':'graph', 'convolution':'mathematics', 'number_theory':'mathematics',
                        'linear_algebra':'mathematics', 'polynomial':'mathematics', 'enumerative_combinatorics':'mathematics',
                        'big_integer':'mathematics', 'set_power_series':'mathematics', 'other':'techniques', 'test':'techniques'},
    'kactl': {'data-structures':'data-structures', 'geometry':'geometry', 'graph':'graph',
              'strings':'strings', 'number-theory':'mathematics', 'numerical':'mathematics', 'combinatorial':'mathematics'},
}


def category(source):
    # Other providers (e.g. curated blogs and USACO difficulty levels) have
    # no comparable taxonomy: tags come from the crosswalk, not a default.
    mapping = PROVIDER_CATEGORIES.get(source['provider'])
    if mapping is None:
        return None
    group = source['id'].split(':', 1)[1].split('/')[0]
    if group not in mapping:
        raise ValueError(f"Unmapped upstream category: {source['provider']}:{group} ({source['id']})")
    return mapping[group]


def compose(root=ROOT):
    local = read(local_path(root, 'index.json'))
    providers, all_sources = sources(root)
    source_by_id = unique_rows(all_sources, 'Sources')
    crosswalk = read(local_path(root, 'knowledge/crosswalk.json'))
    notes = read(local_path(root, 'knowledge/review.json'))
    categories = {**local['categories'], **EXTRA}
    algorithms = {key: dict(t, sources=[], review='local-reference')
                  for key, t in unique_rows(local['topics'], 'Legacy topics').items()}
    claimed = set()
    for key, row in unique_rows(crosswalk, 'Crosswalk').items():
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
            raise ValueError(f'Invalid canonical ID: {key}')
        if key not in algorithms:
            algorithms[key] = dict(id=key, title=row['title'], category=row['category'], aliases=[], review='sources-only')
        card = algorithms[key]
        card['aliases'] = card['aliases'] + row['aliases']
        card['associations'] = row['sources'][:]
        card['sources'] = [a['source'] for a in row['sources']]
        claimed.update(a['source'] for a in row['sources'] if a['relation'] != 'unclassified')
    # Unmapped upstream tutorial records remain separate discovery candidates.
    # Do not guess equivalence from a matching filename or translated title.
    for source in all_sources:
        key = source['id']
        if key not in claimed and source['provider'] in ('oi-wiki', 'cp-algorithms') and not key.endswith('/index.md'):
            algorithms[key] = dict(id=key, title=source['title'], category=category(source), aliases=[],
                                   sources=[key], associations=[dict(source=key, relation='unclassified', basis='No canonical mapping confirmed.')], review='sources-only', identity='upstream-candidate')
    reverse = {key: [] for key in source_by_id}
    for key, card in algorithms.items():
        if key in notes:
            card['review'] = notes[key]['status']
        for source in card['sources']:
            reverse[source].append(key)
    return {'categories': categories, 'sources': source_by_id, 'providers': providers,
            'algorithms': algorithms, 'notes': notes, 'reverse': reverse}


def build(root=ROOT):
    # The CLI cannot bypass the authoring gate by skipping check_quality.py.
    from catalog_quality import check_sources
    issues = check_sources(root)
    if issues:
        raise ValueError('Invalid Catalog:\n' + '\n'.join(issues))
    return compose(root)


def related(data, key):
    card = data['algorithms'][key]
    shared = {k for source in card['sources'] for k in data['reverse'][source] if k != key}
    authored = set(data['notes'].get(key, {}).get('related', []))
    authored.update(k for k, note in data['notes'].items() if key in note['related'])
    return {'editorial': sorted(authored), 'shared_source': sorted(shared - authored)}


def source_view(data, sid):
    row = data['sources'][sid]
    algorithms = sorted(data['reverse'][sid])
    profile = data['providers'][row['provider']]
    categories = {data['algorithms'][key]['category'] for key in algorithms}
    if row['provider'] in ('oi-wiki', 'cp-algorithms', 'library-checker', 'kactl'):
        categories.add(category(row))
    attribution = row['authors'] or [profile['title'] + ' contributors (see per-page history)']
    return dict(row, algorithms=algorithms, tags=sorted(set(algorithms) | categories), attribution=attribution,
                associations=[dict(a, algorithm=key) for key in algorithms for a in data['algorithms'][key].get('associations', []) if a['source'] == sid],
                policy_url=profile['policy_url'], license_url=profile['license_url'],
                permissions=profile['permissions'], license_terms=profile['terms'],
                redistribution_policy=row['mode'], provider_policy=profile['mode'])
