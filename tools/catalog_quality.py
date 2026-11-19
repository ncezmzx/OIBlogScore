"""Audit provenance, local evidence separation and immutable source packaging."""
from collections import Counter
from datetime import date
import hashlib
import re
from urllib.parse import quote, urlsplit

from catalog_data import build, normalize, read, sources


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
        if not ID.fullmatch(pid) or not https(profile['url']) or not profile.get('license'):
            issues.append(pid + ': invalid provider identity/license')
        if set(profile['permissions']) != {'copy', 'modify', 'redistribute'} or set(profile['permissions'].values()) - {'license-conditional', 'not-established'}:
            issues.append(pid + ': invalid redistribution permissions')
        if profile.get('repository') and (not re.fullmatch('[0-9a-f]{40}', profile['revision']) or not HEX.fullmatch(profile['policy_sha256']) or not https(profile['policy_url'])):
            issues.append(pid + ': invalid pinned license metadata')
    ids, urls, digests = set(), set(), {}
    allowlisted_copies = set(policy['cp-algorithms'])
    observed_copies = set()
    for row in records:
        key, pid = row['id'], row['provider']
        profile = providers[pid]
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
        key, refs = row['id'], row['sources']
        if not ID.fullmatch(key) or not refs or len(refs) != len(set(refs)) or set(refs) - ids:
            issues.append(key + ': missing, repeated or unresolved evidence links')
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
    for key, note in notes.items():
        if (key not in data['algorithms'] or note['status'] != 'project-analysis' or len(set(note['checks'])) < 2
                or not note['model'].strip() or not note['witness'].strip()
                or set(note['related']) - data['algorithms'].keys() or key in note['related']):
            issues.append(key + ': incomplete or untraceable project reasoning')
    return issues
