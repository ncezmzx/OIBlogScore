"""Audit provenance, local evidence separation and immutable source packaging."""
from collections import Counter
from datetime import date
import hashlib
import re
from urllib.parse import quote, urlsplit

from catalog_schema import LICENSES, check_record, matches_url, safe_path, terms
from catalog_data import RELATIONS, build, normalize, read, sources


HEX = re.compile(r'[0-9a-f]{64}')
ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def https(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    p = urlsplit(value)
    return (p.scheme == 'https' and bool(p.hostname) and p.netloc == p.hostname
            and not p.fragment and '.' in p.hostname)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_sources(root):
    directory = root / 'sources'
    if not directory.is_dir():
        return ['Missing sources layer']
    providers, records = sources(root)
    policy = read(directory / 'import-policy.json')
    approvals = read(directory / 'approved-verbatim.json')
    notes = read(root / 'knowledge/review.json')
    crosswalk = read(root / 'knowledge/crosswalk.json')
    issues = []
    expected_assets = {'upstream/cp-algorithms/LICENSE.txt'}
    for pid, profile in providers.items():
        if not ID.fullmatch(pid) or not https(profile['url']) or profile.get('license') not in LICENSES:
            issues.append(pid + ': invalid provider identity/license')
        if set(profile['permissions']) != {'copy', 'modify', 'redistribute'} or set(profile['permissions'].values()) - {'license-conditional', 'not-established'}:
            issues.append(pid + ': invalid redistribution permissions')
        if profile.get('repository') and (not re.fullmatch('[0-9a-f]{40}', profile['revision']) or not HEX.fullmatch(profile['policy_sha256']) or not https(profile['policy_url'])):
            issues.append(pid + ': invalid pinned license metadata')
        expected_permission = 'not-established' if profile.get('license') in ('not-established','file-specific') else 'license-conditional'
        if any(value != expected_permission for value in profile['permissions'].values()):
            issues.append(pid + ': permissions conflict with stated license policy')
        if profile.get('license') in LICENSES and profile.get('terms') != terms(profile['license']):
            issues.append(pid + ': incorrect commercial-use, attribution or ShareAlike terms')
        if profile.get('mode') != ('selected-verbatim' if pid == 'cp-algorithms' else 'metadata-only'):
            issues.append(pid + ': invalid redistribution policy')
        if pid == 'cp-algorithms' and (profile.get('license') != 'CC-BY-SA-4.0' or profile.get('license_url') != 'https://creativecommons.org/licenses/by-sa/4.0/' or not all(v == 'license-conditional' for v in profile['permissions'].values())):
            issues.append(pid + ': missing effective permission for approved copies')
        if profile.get('repository') and (not safe_path(profile['policy_path']) or profile['policy_url'] != 'https://github.com/{repository}/blob/{revision}/'.format(**profile) + quote(profile['policy_path'])):
            issues.append(pid + ': license policy URL does not match pinned path')
    ids, urls, digests = set(), set(), {}
    cohort = read(root / 'knowledge/triage-baseline.json')
    allowlisted_copies = set(policy['cp-algorithms'])
    observed_copies = set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get('provider'), str) or row['provider'] not in providers:
            issues.append('Unknown source provider or malformed source record')
            continue
        pid = row['provider']
        profile = providers[pid]
        errors = check_record(row, profile)
        if errors:
            issues.extend(f'{row.get("id", pid)}: {error}' for error in errors)
            continue
        key = row['id']
        if row.get('metadata_evidence') and not https(row['metadata_evidence']):
            issues.append(key + ': malformed metadata evidence URL')
        if pid == 'codeforces' and (not re.fullmatch(r'codeforces:[0-9]+', key) or urlsplit(row['url']).path != '/blog/entry/' + key.split(':',1)[1]
                                    or any(not isinstance(a,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', a) for a in row['authors'])):
            issues.append(key + ': invalid Codeforces article ID or author handle')
        if row.get('published') is not None:
            date.fromisoformat(row['published'])
        url = row['url']
        if key in ids or url in urls or not key.startswith(pid + ':') or not https(url) or urlsplit(url).hostname != urlsplit(profile['url']).hostname:
            issues.append(key + ': duplicate ID/URL or invalid URL/provider')
        ids.add(key)
        urls.add(url)
        if (row['license'] != profile['license'] or row['modified'] is not False or row['trust'] != 'upstream-unreviewed'
                or not row['title'].strip() or not row['original_language'] or not row['content_language']
                or not isinstance(row['authors'], list) or any(not isinstance(a, str) or not a.strip() for a in row['authors'])):
            issues.append(key + ': invalid attribution, license or trust separation')
        date.fromisoformat(row['retrieved'])
        if 'repository' in profile:
            repo = 'https://github.com/' + profile['repository']
            path = row['path']
            if not matches_url(pid, profile, row):
                issues.append(key + ': source ID, website URL and pinned path do not correspond')
            rev = profile['revision']
            for label, url_part in (('permalink','blob'), ('history','commits')):
                if row[label] != f'{repo}/{url_part}/{rev}/{quote(path)}':
                    issues.append(key + ': invalid pinned ' + label)
            if row['revision'] != rev or not HEX.fullmatch(row['sha256']) or row['retrieved'] != profile['retrieved']:
                issues.append(key + ': invalid upstream snapshot')
            if row['sha256'] in digests and row['mode'] == 'verbatim':
                issues.append(key + ': duplicate imported payload: ' + digests[row['sha256']])
            digests[row['sha256']] = key
        elif not (row.get('scope', '').strip() and row.get('review_use', '').strip() and row.get('authors')):
            issues.append(key + ': curated record requires author, actual scope and review application')
        if row['mode'] == 'verbatim':
            rel = key.split(':',1)[1]
            relative = 'upstream/cp-algorithms/' + rel + '.txt'
            if (pid != 'cp-algorithms' or profile['mode'] != 'selected-verbatim' or rel not in allowlisted_copies
                    or approvals.get(rel) != row['sha256'] or row.get('text_path') != relative or '..' in relative.split('/')):
                issues.append(key + ': unsafe or unapproved verbatim text')
                continue
            expected_assets.add(relative)
            observed_copies.add(rel)
            path = directory / relative
            if not path.is_file() or path.is_symlink() or checksum(path) != row['sha256']:
                issues.append(key + ': missing or modified upstream text')
        elif row['mode'] != 'external-index' or 'text_path' in row:
            issues.append(key + ': disallowed redistribution mode')
    if not re.fullmatch('[0-9a-f]{40}', cohort['revision']) or len(cohort['source_ids']) != len(set(cohort['source_ids'])) or set(cohort['source_ids']) - ids:
        issues.append('Invalid baseline cohort')
    assets = {p.relative_to(directory).as_posix() for p in (directory/'upstream').rglob('*') if p.is_file()}
    if assets != expected_assets or observed_copies != allowlisted_copies or observed_copies != approvals.keys():
        issues.append('Untracked or missing upstream assets/allowlist entries')
    license_file = directory / 'upstream/cp-algorithms/LICENSE.txt'
    if license_file.exists() and checksum(license_file) != providers['cp-algorithms']['policy_sha256']:
        issues.append('Bundled CC BY-SA license differs from pinned original')
    collisions = Counter(row['id'] for row in crosswalk)
    if any(count != 1 for count in collisions.values()):
        issues.append('Duplicate canonical algorithm ID')
    for row in crosswalk:
        key = row['id']
        refs = [a['source'] for a in row['sources']]
        if not ID.fullmatch(key) or not refs or len(refs) != len(set(refs)) or set(refs) - ids:
            issues.append(key + ': missing, repeated or unresolved evidence links')
    owners = {}
    for row in crosswalk:
        for a in row['sources']:
            if set(a) != {'source', 'relation', 'basis'} or a['relation'] not in RELATIONS or not a['basis'].strip():
                issues.append(row['id'] + ': invalid association or missing rationale')
            if a['relation'] in {'exact', 'alias'}:
                previous = owners.setdefault(a['source'], row['id'])
                if previous != row['id']:
                    issues.append(a['source'] + ': conflicting identity claims: ' + previous + ', ' + row['id'])
    if issues:
        return issues
    data = build(root)
    aliases = {}
    for key, card in data['algorithms'].items():
        if card['category'] not in data['categories']:
            issues.append(key + ': unknown category')
        if card.get('identity') == 'upstream-candidate':
            continue
        for alias in (key, card['title'], *card['aliases']):
            norm = normalize(alias)
            if not norm or norm in aliases and aliases[norm] != key:
                issues.append(key + ': duplicate/empty canonical name: ' + alias)
            aliases[norm] = key
        if not card['sources']:
            issues.append(key + ': no traceable sources')
        if card.get('path') and (root/card['path']).is_file():
            body = (root/card['path']).read_text(encoding='utf-8')
            urls = set(re.findall(r'\]\((https://[^)]+)\)', body))
            known = {data['sources'][sid]['url'] for sid in card['sources']}
            if urls - known:
                issues.append(key + ': local citation missing provenance: ' + ', '.join(sorted(urls - known)))
    used = set()
    fields = {'status','evidence','sources','model','preconditions','invariant','proof','complexity','witness','checks','related'}
    prose = ('model','preconditions','invariant','proof','complexity','witness')
    for key, note in notes.items():
        card = data['algorithms'].get(key, {})
        if (not isinstance(note, dict) or set(note) != fields or not card or card.get('identity')
                or note['status'] not in {'project-analysis','needs-review'} or note['evidence'] != 'original-derivation'
                or not note['sources'] or set(note['sources']) - set(card['sources'])
                or not isinstance(note['checks'], list) or any(not isinstance(v, str) or not v.strip() for v in note['checks'])
                or len(set(note['checks'])) < 2
                or set(note['related']) - data['algorithms'].keys() or key in note['related']):
            issues.append(key + ': incomplete or untraceable project reasoning')
            continue
        for field in prose:
            value = note[field]
            if not isinstance(value, str) or not value.strip() or normalize(value) in {'todo','tbd','待补','略','未完成','n/a'}:
                issues.append(f'{key}: empty/template {field}')
            elif normalize(value) in used:
                issues.append(f'{key}: duplicate review prose ({field})')
            else:
                used.add(normalize(value))
        if not re.search(r'O\(|Θ\(|Ω\(|ceil|floor|Σ', note['complexity']):
            issues.append(key + ': complexity requires an explicit bound or work expression')
    return issues
