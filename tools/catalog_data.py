"""Pure catalog composition: upstream facts are not accepted audit conclusions."""
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1] / 'resources' / 'algorithm-catalog'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def sources(root=ROOT):
    directory = root / 'sources'
    providers = read(directory / 'providers.json')
    return providers, [row for filename in sorted(directory.glob('*.json'))
                       if filename.stem in providers or filename.stem == 'curated'
                       for row in read(filename)]


EXTRA = {'geometry': '计算几何', 'foundations': '基础算法、贪心与构造', 'search': '搜索与剪枝',
         'randomized': '随机化', 'techniques': '交互与实战技巧'}
OI_CATEGORIES = dict(basic='foundations', contest='techniques', dp='dp', ds='data-structures',
                     geometry='geometry', graph='graph', lang='techniques', math='mathematics',
                     misc='techniques', search='search', string='strings', topic='techniques')
CP_CATEGORIES = dict(algebra='mathematics', combinatorics='mathematics', data_structures='data-structures',
                     dynamic_programming='dp', game_theory='mathematics', geometry='geometry', graph='graph',
                     linear_algebra='mathematics', num_methods='foundations', others='techniques',
                     schedules='foundations', sequences='foundations', string='strings')


def category(source):
    rel = source['id'].split(':', 1)[1]
    group = rel.split('/')[0]
    if source['provider'] == 'library-checker':
        return {'data_structure':'data-structures', 'tree':'graph', 'string':'strings', 'geo':'geometry',
                'graph':'graph', 'convolution':'mathematics', 'number_theory':'mathematics',
                'linear_algebra':'mathematics', 'polynomial':'mathematics', 'enumerative_combinatorics':'mathematics',
                'big_integer':'mathematics', 'set_power_series':'mathematics'}.get(group, 'techniques')
    if source['provider'] == 'kactl':
        return {'data-structures':'data-structures', 'geometry':'geometry', 'graph':'graph',
                'string':'strings', 'number-theory':'mathematics', 'numerical':'mathematics',
                'combinatorial':'mathematics'}.get(group, 'techniques')
    return (OI_CATEGORIES if source['provider'] == 'oi-wiki' else CP_CATEGORIES).get(group, 'techniques')


def build(root=ROOT):
    local = read(root / 'index.json')
    providers, all_sources = sources(root)
    source_by_id = {record['id']: record for record in all_sources}
    crosswalk = read(root / 'knowledge' / 'crosswalk.json')
    notes = read(root / 'knowledge' / 'review.json')
    categories = {**local['categories'], **EXTRA}
    algorithms = {t['id']: dict(t, sources=[], review='local-reference') for t in local['topics']}
    claimed = set()
    for row in crosswalk:
        key = row['id']
        if key not in algorithms:
            algorithms[key] = dict(id=key, title=row['title'], category=row['category'], aliases=[], review='sources-only')
        card = algorithms[key]
        card['aliases'] = list(dict.fromkeys(card['aliases'] + row['aliases']))
        card['sources'] = row['sources'][:]
        claimed.update(row['sources'])
    # Unmapped upstream tutorial records remain separate discovery candidates.
    # Do not guess equivalence from a matching filename or translated title.
    for source in all_sources:
        key = source['id']
        if key not in claimed and source['provider'] in ('oi-wiki', 'cp-algorithms') and not key.endswith('/index.md'):
            algorithms[key] = dict(id=key, title=source['title'], category=category(source), aliases=[],
                                   sources=[key], review='sources-only', identity='upstream-candidate')
    reverse = {key: [] for key in source_by_id}
    for key, card in algorithms.items():
        if key in notes:
            card['review'] = 'project-analysis'
        for source in card['sources']:
            reverse[source].append(key)
    return {'categories': categories, 'sources': source_by_id, 'providers': providers,
            'algorithms': algorithms, 'notes': notes, 'reverse': reverse}


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
                policy_url=profile['policy_url'], license_url=profile['license_url'],
                permissions=profile['permissions'], redistribution_policy=profile['mode'])
