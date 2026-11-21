"""Audit provenance, local evidence separation and immutable source packaging."""
from datetime import date
import hashlib
import re
from urllib.parse import quote, urlsplit

from catalog_io import local_path, read_text
from catalog_schema import LAYOUTS, LICENSES, check_claims, check_record, matches_url, safe_path, terms
from catalog_data import EXTRA, RELATIONS, category, name_key, normalize, read, sources


HEX = re.compile(r'[0-9a-f]{64}')
ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
THIRD_PARTY = re.compile(
    r'(taken from (?:the )?(?:paper|book|article)|reprinted from|adapted from|all rights reserved|used with permission)',
    re.I)


def https(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    p = urlsplit(value)
    return (p.scheme == 'https' and bool(p.hostname) and p.netloc == p.hostname
            and not p.fragment and '.' in p.hostname)


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _check_sources(root, issues):
    directory = root / 'sources'
    if not directory.is_dir():
        issues.append('Missing sources layer')
        return issues
    providers, records = sources(root)
    policy = read(local_path(root, 'sources/import-policy.json'))
    approvals = read(local_path(root, 'sources/approved-verbatim.json'))
    pins = read(local_path(root, 'sources/verbatim-pin.json'))
    if not isinstance(pins, dict):
        issues.append('Verbatim pin record must be an object')
        pins = {}
    expected_assets = {'upstream/cp-algorithms/LICENSE.txt'}
    common = set('title url license license_url mode permissions policy_url retrieved terms'.split())
    pinned = set('language policy_path policy_sha256 repository revision'.split())
    invalid_profiles = set()
    for pid, profile in providers.items():
        expected = common | (pinned if pid in LAYOUTS else set())
        if (not isinstance(profile, dict) or profile.keys() != expected
                or any(not isinstance(profile[k], str) or not profile[k].strip()
                       for k in expected - {'license_url','policy_url','permissions','terms'})
                or not isinstance(profile['permissions'], dict) or not isinstance(profile['terms'], dict)
                or any(profile[k] is not None and not https(profile[k]) for k in ('license_url','policy_url'))):
            issues.append(pid + ': malformed provider schema')
            invalid_profiles.add(pid)
            continue
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
        if profile.get('mode') == 'selected-verbatim':
            pin = pins.get(pid)
            expected = {'revision': profile['revision'], 'policy_sha256': profile['policy_sha256']}
            if pin != expected:
                issues.append(pid + ': verbatim approval is not bound to the current provider pin')
    selected = {pid for pid, profile in providers.items() if profile.get('mode') == 'selected-verbatim'}
    if set(pins) != selected:
        issues.append('Verbatim pin record must cover exactly the selected-verbatim providers')
    ids, urls, digests = set(), set(), {}
    allowlisted_copies = set(policy['cp-algorithms'])
    observed_copies = set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get('provider'), str) or row['provider'] not in providers:
            issues.append('Unknown source provider or malformed source record')
            continue
        pid = row['provider']
        if pid in invalid_profiles:
            continue
        profile = providers[pid]
        errors = check_record(row, profile)
        if errors:
            issues.extend(f'{row.get("id", pid)}: {error}' for error in errors)
            continue
        key = row['id']
        try:
            category(row)
        except ValueError as exc:
            issues.append(str(exc))
        if row.get('metadata_evidence') and not https(row['metadata_evidence']):
            issues.append(key + ': malformed metadata evidence URL')
        if pid == 'codeforces' and (not re.fullmatch(r'codeforces:[0-9]+', key) or urlsplit(row['url']).path != '/blog/entry/' + key.split(':',1)[1]
                                    or any(not isinstance(a,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', a) for a in row['authors'])):
            issues.append(key + ': invalid Codeforces article ID or author handle')
        for field in ('published', 'retrieved'):
            if row.get(field) is not None:
                try:
                    date.fromisoformat(row[field])
                except ValueError:
                    issues.append(key + ': invalid calendar date: ' + field)
        url = row['url']
        if key in ids or url in urls or not key.startswith(pid + ':') or not https(url) or urlsplit(url).hostname != urlsplit(profile['url']).hostname:
            issues.append(key + ': duplicate ID/URL or invalid URL/provider')
        ids.add(key)
        urls.add(url)
        if (row['license'] != profile['license'] or row['modified'] is not False or row['trust'] != 'upstream-unreviewed'
                or not row['title'].strip() or not row['original_language'] or not row['content_language']
                or not isinstance(row['authors'], list) or any(not isinstance(a, str) or not a.strip() for a in row['authors'])):
            issues.append(key + ': invalid attribution, license or trust separation')
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
            path = local_path(root, "sources/" + relative)
            if not path.is_file() or path.is_symlink() or checksum(path) != row['sha256']:
                issues.append(key + ': missing or modified upstream text')
            else:
                try:
                    text = read_text(path)
                except (ValueError, OSError) as exc:
                    issues.append(key + ': invalid verbatim text: ' + str(exc))
                else:
                    if THIRD_PARTY.search(text):
                        issues.append(key + ': verbatim text contains third-party provenance markers; review the license or use external-index')
        elif row['mode'] != 'external-index' or 'text_path' in row:
            issues.append(key + ': disallowed redistribution mode')
    assets = {p.relative_to(directory).as_posix() for p in (directory/'upstream').rglob('*') if p.is_file()}
    if assets != expected_assets or observed_copies != allowlisted_copies or observed_copies != approvals.keys():
        issues.append('Untracked or missing upstream assets/allowlist entries')
    license_file = local_path(root, 'sources/upstream/cp-algorithms/LICENSE.txt')
    if 'cp-algorithms' in providers and 'cp-algorithms' not in invalid_profiles and license_file.is_file() and checksum(license_file) != providers['cp-algorithms']['policy_sha256']:
        issues.append('Bundled CC BY-SA license differs from pinned original')
    return issues


def check_knowledge(root, issues):
    manifest = read(local_path(root, 'index.json'))
    crosswalk = read(local_path(root, 'knowledge/crosswalk.json'))
    notes = read(local_path(root, 'knowledge/review.json'))
    cohort = read(local_path(root, 'knowledge/triage-baseline.json'))
    try:
        _, raw = sources(root)
        sources_by_id = {row['id']: row for row in raw}  # sources() rejects duplicates first
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Source validation has its own diagnostic. Continue local checks.
        sources_by_id = None
    ids = None if sources_by_id is None else set(sources_by_id)
    baseline = cohort['source_ids']
    if (not re.fullmatch('[0-9a-f]{40}', cohort['revision']) or not isinstance(baseline, list)
            or len(baseline) != len(set(baseline)) or (ids is not None and set(baseline) - ids)):
        issues.append('Invalid baseline cohort')
    categories = set(manifest['categories']) | set(EXTRA)
    cards, owners, names = {}, {}, {}
    for topic in manifest['topics']:
        key = topic['id']
        if key in cards or not ID.fullmatch(key):
            issues.append(key + ': invalid or duplicate legacy algorithm ID')
            continue
        cards[key] = dict(topic, refs=[], legacy=True)
    seen = set()
    if not isinstance(crosswalk, list):
        issues.append('Crosswalk must be an array')
        crosswalk = []
    for row in crosswalk:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            issues.append('Malformed crosswalk record')
            continue
        key = row['id']
        if key in seen or not ID.fullmatch(key):
            issues.append(key + ': invalid or duplicate ID in Crosswalk')
            continue
        seen.add(key)
        base = cards.get(key)
        fields = {'id','aliases','sources'} | (set() if base else {'title','category'})
        if set(row) != fields or not isinstance(row['aliases'], list) or not isinstance(row['sources'], list):
            issues.append(key + ': malformed crosswalk fields or legacy metadata override')
            continue
        if base is None:
            base = cards[key] = dict(title=row['title'], category=row['category'], aliases=[], refs=[])
        base['aliases'] = base['aliases'] + row['aliases']
        for edge in row['sources']:
            if (not isinstance(edge, dict) or set(edge) != {'source','relation','basis'}
                    or any(not isinstance(v, str) or not v.strip() for v in edge.values())
                    or edge['relation'] not in RELATIONS):
                issues.append(key + ': invalid association or missing rationale')
                continue
            sid = edge['source']
            if sid in base['refs'] or (ids is not None and sid not in ids):
                issues.append(key + ': missing, repeated or unresolved evidence links: ' + sid)
            base['refs'].append(sid)
            if edge['relation'] in {'exact','alias'}:
                previous = owners.setdefault(sid, key)
                if previous != key:
                    issues.append(sid + ': conflicting identity claims: ' + previous + ', ' + key)
    for key, card in cards.items():
        if not isinstance(card['category'], str) or card['category'] not in categories:
            issues.append(key + ': unknown category')
        elif card.get('legacy'):
            path = card.get('path')
            expected = card['category'] + '/' + key + '.md'
            if not isinstance(path, str) or not path:
                issues.append(key + ': legacy topic requires a path')
            elif path != expected:
                issues.append(key + ': legacy topic path does not match category/id')
        aliases = card['aliases']
        if not isinstance(aliases, list) or any(not isinstance(a,str) or not a.strip() for a in aliases):
            issues.append(key + ': invalid aliases')
            aliases = []
        normalized = [name_key(a) for a in aliases]
        if len(set(normalized)) != len(normalized):
            issues.append(key + ': duplicate normalized alias within algorithm')
        title = card['title']
        if not isinstance(title,str) or not title.strip():
            issues.append(key + ': invalid canonical title')
            title = ''
        for alias in aliases:
            norm = name_key(alias)
            if not norm or names.setdefault(norm, key) != key or (normalize(alias) in cards and normalize(alias) != key):
                issues.append(key + ': duplicate/empty canonical name: ' + alias)
        if not card['refs']:
            issues.append(key + ': no traceable sources')
        if card.get('path') and sources_by_id is not None:
            try:
                body = read_text(local_path(root, card['path']))
                urls = set(re.findall(r'\]\((https://[^)]+)\)', body))
                known = {sources_by_id[sid]['url'] for sid in card['refs'] if sid in sources_by_id}
                if urls - known:
                    issues.append(key + ': local citation missing provenance: ' + ', '.join(sorted(urls - known)))
            except (OSError, ValueError) as exc:
                issues.append(key + ': unreadable local topic: ' + str(exc))
    used = set()
    fields = {'status','evidence','sources','model','preconditions','invariant','proof','complexity','witness','checks','related'}
    prose = ('model','preconditions','invariant','proof','complexity','witness')
    for key, note in notes.items():
        card = cards.get(key, {})
        if (not isinstance(note, dict) or (fields - note.keys() or note.keys() - fields - {'claims'}) or not card or card.get('identity')
                or not isinstance(note['status'], str) or note['status'] not in {'project-analysis','needs-review'} or note['evidence'] != 'original-derivation'
                or not isinstance(note['sources'], list) or not note['sources']
                or any(not isinstance(s, str) for s in note['sources'])
                or len(set(note['sources'])) != len(note['sources']) or set(note['sources']) - set(card['refs'])
                or not isinstance(note['checks'], list) or any(not isinstance(v, str) or not v.strip() for v in note['checks'])
                or len(set(note['checks'])) < 2
                or not isinstance(note['related'], list) or any(not isinstance(s, str) for s in note['related'])
                or len(set(note['related'])) != len(note['related']) or set(note['related']) - cards.keys() or key in note['related']):
            issues.append(key + ': incomplete or untraceable project reasoning')
            continue
        issues.extend(f'{key}: {error}' for error in check_claims(note.get('claims', []), set(note['sources'])))
        for field in prose:
            value = note[field]
            if not isinstance(value, str) or not value.strip() or normalize(value) in {'todo','tbd','待补','略','未完成','n/a'}:
                issues.append(f'{key}: empty/template {field}')
            elif normalize(value) in used:
                issues.append(f'{key}: duplicate review prose ({field})')
            else:
                used.add(normalize(value))
        if isinstance(note['complexity'], str) and not re.search(r'O\(|Θ\(|Ω\(|ceil|floor|Σ', note['complexity']):
            issues.append(key + ': complexity requires an explicit bound or work expression')
    return issues


def check_sources(root):
    issues = []
    for phase in (_check_sources, check_knowledge):
        try:
            phase(root, issues)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            issues.append(f'{phase.__name__}: {exc}')
    return issues
