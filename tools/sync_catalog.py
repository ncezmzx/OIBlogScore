#!/usr/bin/env python3
"""Read pinned Git objects and stage a new source snapshot, never edit the catalog."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import shutil
from tempfile import TemporaryDirectory
import sys
from urllib.parse import quote

from catalog_schema import LAYOUTS
from catalog_io import local_path, read as load, unique_rows


ROOT = Path(__file__).resolve().parents[1] / 'resources' / 'algorithm-catalog' / 'sources'
OI_GROUPS = set('basic contest dp ds geometry graph lang math misc search string topic'.split())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], stderr=subprocess.PIPE)


def records(provider, config, checkout, policy):
    revision = config['revision']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('A full commit SHA is required')

    def read(path):
        return git(checkout, 'show', revision + ':' + path)

    license_bytes = read(config['policy_path'])
    if sha(license_bytes) != config['policy_sha256']:
        raise ValueError(provider + ': license declaration changed; review before updating the pinned hash')
    paths = git(checkout, 'ls-tree', '-r', '-z', '--name-only', revision).decode().strip('\0').split('\0')
    paths = [n for n in paths if n.startswith(LAYOUTS[provider])]
    nav = {}
    if provider == 'oi-wiki':
        for title, path in re.findall(r'^\s*-\s+(.+?):\s+(\S+\.md)\s*$', read('mkdocs.yml').decode(), re.M):
            nav[path] = title.strip('"\'')
    rows, assets, seen_allowlist = [], {}, set()
    allowlist = set(policy.get(provider, []))
    base = f"https://github.com/{config['repository']}"
    for path in paths:
        rel = path[len(LAYOUTS[provider]):]
        folder, _, name = rel.rpartition('/')
        if provider == 'oi-wiki' and (not path.endswith('.md') or folder.split('/')[0] not in OI_GROUPS):
            continue
        if provider == 'cp-algorithms' and (not path.endswith('.md') or not folder):
            continue
        if provider == 'usaco-guide' and not path.endswith('.mdx'):
            continue
        if provider == 'library-checker' and (not path.endswith('/info.toml') or path.count('/') != 2 or path.startswith('sample/')):
            continue
        if provider == 'kactl' and (not path.endswith('.h') or folder in ('contest', 'various')):
            continue
        raw = read(path)
        text = raw.decode('utf-8', errors='replace')
        stem = Path(name).stem
        authors = []
        if provider == 'oi-wiki':
            url = config['url'] + quote((folder + '/') if stem == 'index' else rel[:-3] + '/')
            title = nav.get(rel, stem.replace('-', ' '))
        elif provider == 'cp-algorithms':
            url = config['url'] + quote(rel[:-3]) + '.html'
            heading = re.search(r'^#\s+([^\n]+)', text, re.M)
            title = heading[1].strip() if heading else stem.replace('-', ' ').replace('_', ' ')
        elif provider == 'usaco-guide':
            fields = dict(re.findall(r'^(id|title|author):[ \t]*(.+)$', text.split('---', 2)[1] if text.startswith('---') else '', re.M))
            if fields.get('id') not in allowlist or 'title' not in fields:
                continue
            seen_allowlist.add(fields['id'])
            levels = {'1_General':'general', '2_Bronze':'bronze', '3_Silver':'silver', '4_Gold':'gold', '5_Plat':'plat', '6_Advanced':'adv'}
            level = levels.get(folder.split('/')[0])
            if not level:
                raise ValueError('Unknown USACO module level: '+folder)
            url = f"{config['url']}{level}/{fields['id']}"
            title = fields['title'].strip('"\'')
            authors = [fields['author'].strip('"\'')] if fields.get('author') else []
        elif provider == 'library-checker':
            title_match = re.search(r'''^title\s*=\s*(?:"([^"\n]+)"|'([^'\n]+)')''', text, re.M)
            if not title_match:
                continue
            title = title_match[1] or title_match[2]
            url = config['url'] + 'problem/' + folder.rsplit('/', 1)[-1]
        else:
            title = stem
            url = f'{base}/blob/{revision}/{quote(path)}'
            author = re.search(r'^\s*\*\s*Author:\s*(.+)', text, re.M)
            authors = [author[1].strip()] if author else []
        mode = 'external-index'
        if provider == 'cp-algorithms' and rel in allowlist:
            seen_allowlist.add(rel)
            # Preserve bytes and upstream notices. A license override requires manual review.
            if re.search(r'^\s*(?:license|copyright)\s*:', text, re.M | re.I):
                raise ValueError('In-page license notice requires review: ' + path)
            mode = 'verbatim'
            assets['upstream/cp-algorithms/' + rel + '.txt'] = raw
        row = dict(id=provider + ':' + rel, provider=provider, title=title, url=url, path=path,
                   revision=revision, sha256=sha(raw), authors=authors, license=config['license'],
                   original_language=config['language'], content_language=config['language'],
                   mode=mode, modified=False, trust='upstream-unreviewed', retrieved=config['retrieved'],
                   kind={'library-checker':'judge-problem','kactl':'implementation'}.get(provider,'tutorial'),
                   permalink=f'{base}/blob/{revision}/{quote(path)}', history=f'{base}/commits/{revision}/{quote(path)}')
        if mode == 'verbatim':
            row['text_path'] = 'upstream/cp-algorithms/' + rel + '.txt'
        rows.append(row)
    if allowlist != seen_allowlist:
        raise ValueError(provider + ': missing allowlisted entries: ' + ', '.join(sorted(allowlist - seen_allowlist)))
    if assets:
        assets['upstream/cp-algorithms/LICENSE.txt'] = license_bytes
    return sorted(rows, key=lambda r: r['id']), assets


def changes(old, new):
    a = unique_rows(old, 'Current source snapshot')
    b = unique_rows(new, 'Candidate source snapshot')
    added, removed = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
    old_hash, new_hash = {}, {}
    for key in removed:
        old_hash.setdefault(a[key]['sha256'], []).append(key)
    for key in added:
        new_hash.setdefault(b[key]['sha256'], []).append(key)
    renames = [dict(old=keys[0], new=new_hash[d][0]) for d, keys in old_hash.items()
               if len(keys) == 1 and len(new_hash.get(d, [])) == 1]
    return {'added': added, 'removed': removed,
            'possible_renames': sorted(renames, key=lambda item: item['old']),
            'content_changed': sorted(k for k in a.keys() & b.keys() if a[k]['sha256'] != b[k]['sha256']),
            'metadata_changed': sorted(k for k in a.keys() & b.keys() if a[k] != b[k] and a[k]['sha256'] == b[k]['sha256'])}


def broken_references(knowledge, removed):
    missing = set(removed)
    crosswalk = load(knowledge / 'crosswalk.json')
    notes = load(knowledge / 'review.json')
    baseline = load(knowledge / 'triage-baseline.json')['source_ids']
    return {'crosswalk': sorted((row['id'], a['source']) for row in crosswalk for a in row['sources'] if a['source'] in missing),
            'review': sorted((key, sid) for key, note in notes.items() for sid in note['sources'] if sid in missing),
            'triage_baseline': sorted(missing.intersection(baseline))}


def require_valid(root):
    from catalog_quality import check_sources
    issues = check_sources(root)
    if issues:
        raise ValueError('Catalog validation failed:\n' + '\n'.join(issues))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=LAYOUTS)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--output', type=Path, help='new directory only; never overwrites existing files')
    parser.add_argument('--approvals', type=Path, default=ROOT/'approved-verbatim.json', help='reviewed digests of verbatim files')
    parser.add_argument('--providers', type=Path, default=ROOT/'providers.json', help='reviewed candidate pin file')
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError('Output already exists; use a fresh staging directory')
        if args.output and ROOT.parent in (args.output.resolve(), *args.output.resolve().parents):
            raise ValueError('Output must be outside the catalog')
        require_valid(ROOT.parent)
        config = load(args.providers)[args.provider]
        current_config = load(ROOT / 'providers.json')[args.provider]
        permitted = {'revision','policy_sha256','policy_url','retrieved'}
        if {k:v for k,v in config.items() if k not in permitted} != {k:v for k,v in current_config.items() if k not in permitted}:
            raise ValueError('Candidate changes provider identity or licensing policy; review the policy separately')
        if config['policy_url'] != 'https://github.com/{repository}/blob/{revision}/'.format(**config) + quote(config['policy_path']):
            raise ValueError('Candidate policy URL does not match the pinned policy path')
        rows, assets = records(args.provider, config, args.checkout, load(ROOT/'import-policy.json'))
        name = args.provider + '.json'
        old = ROOT / name
        plan = changes(load(old) if old.exists() else [], rows)
        broken = broken_references(ROOT.parent / 'knowledge', plan['removed'])
        plan['reference_conflicts'] = broken
        print(json.dumps(plan, indent=2))
        if any(broken.values()):
            raise ValueError('Candidate snapshot would break local references; review and migrate IDs explicitly')
        candidate_profiles = load(ROOT / 'providers.json')
        candidate_profiles[args.provider] = config
        files = {name: encoded(rows), **assets}
        if args.provider == 'cp-algorithms':
            approved = load(args.approvals)
            imported = {r['id'].split(':', 1)[1]: r['sha256'] for r in rows if r['mode'] == 'verbatim'}
            if imported != approved:
                raise ValueError('Verbatim payloads changed; inspect diff, attribution and license before approving new digests')
            files['approved-verbatim.json'] = encoded(approved)
        if candidate_profiles != load(ROOT / 'providers.json'):
            files['providers.json'] = encoded(candidate_profiles)
        with TemporaryDirectory(prefix='oi-catalog-') as temp:
            candidate = Path(temp) / 'catalog'
            shutil.copytree(ROOT.parent, candidate, symlinks=True)
            for relative, data in files.items():
                p = local_path(candidate, 'sources/' + relative)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            require_valid(candidate)
        if args.output:
            args.output.mkdir(parents=False, exist_ok=False)
            for relative, data in files.items():
                p = local_path(args.output, relative)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open('xb') as stream:
                    stream.write(data)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
