"""Strict, dependency-free schema checks before catalog composition."""
from pathlib import PurePosixPath
import re
from urllib.parse import quote, urlsplit

LAYOUTS = {'oi-wiki': 'docs/', 'cp-algorithms': 'src/', 'usaco-guide': 'content/',
           'library-checker': '', 'kactl': 'content/'}

LICENSES = {
    'CC-BY-SA-4.0': ('conditional', 'required', 'required'),
    'CC-BY-SA-4.0 + SATA': ('conditional', 'required', 'required'),
    'CC-BY-NC-SA-4.0': ('prohibited', 'required', 'required'),
    'Apache-2.0': ('conditional', 'required', 'not-required'),
    'file-specific': ('unknown', 'unknown', 'unknown'),
    'not-established': ('unknown', 'unknown', 'unknown'),
}
BASE = set('id provider title url authors license original_language content_language mode modified trust retrieved kind'.split())
PIN = set('path revision sha256 permalink history'.split())
CURATED = set('published scope review_use metadata_status'.split())
KINDS = {'tutorial', 'judge-problem', 'implementation', 'blog', 'editorial', 'paper'}


def terms(license_id):
    return dict(zip(('commercial_use', 'attribution', 'share_alike'), LICENSES[license_id]))


def safe_path(value):
    return (isinstance(value, str) and value and not value.startswith('/') and '\\' not in value
            and all(p not in ('', '.', '..') for p in value.split('/')))


def matches_url(provider, profile, row):
    path = row['path']
    root = LAYOUTS[provider]
    if not safe_path(path) or not path.startswith(root):
        return False
    relative = path[len(root):]
    base = profile['url']
    if row['id'] != provider + ':' + relative:
        return False
    name = PurePosixPath(relative)
    if provider == 'oi-wiki':
        suffix = str(name.parent) + '/' if name.name == 'index.md' else relative[:-3] + '/'
        return name.suffix == '.md' and row['url'] == base + quote(suffix)
    if provider == 'cp-algorithms':
        return name.suffix == '.md' and row['url'] == base + quote(relative[:-3]) + '.html'
    if provider == 'library-checker':
        return name.name == 'info.toml' and row['url'] == base + 'problem/' + name.parent.name
    if provider == 'kactl':
        return name.suffix == '.h' and row['url'] == row['permalink']
    level = {'1_General':'general','2_Bronze':'bronze','3_Silver':'silver','4_Gold':'gold','5_Plat':'plat','6_Advanced':'adv'}.get(name.parts[0])
    # The USACO slug is stored in upstream frontmatter, not encoded in its path.
    return (name.suffix == '.mdx' and level and row['url'].startswith(base + level + '/')
            and re.fullmatch(r'[A-Za-z0-9_-]+', row['url'].rsplit('/', 1)[-1]) is not None
            and row['url'].count('/') == (base + level + '/').count('/'))


def check_record(row, profile):
    if not isinstance(row, dict):
        return ['Source record must be an object']
    fields = BASE | (PIN if profile.get('repository') else CURATED)
    optional = {'text_path'} if profile.get('repository') else {'metadata_evidence'}
    if fields - row.keys() or row.keys() - fields - optional:
        return ['missing or unknown source fields: ' + ', '.join(sorted((fields - row.keys()) | (row.keys() - fields - optional)))]
    string_fields = fields - {'authors','modified','published'}
    if any(not isinstance(row[k], str) or not row[k].strip() for k in string_fields):
        return ['blank or non-string source field']
    if (type(row['modified']) is not bool or not isinstance(row['authors'], list)
            or row['kind'] not in KINDS or row['mode'] not in ('verbatim', 'external-index')):
        return ['invalid source type, kind or mode']
    if not profile.get('repository'):
        if (row['published'] is not None and (not isinstance(row['published'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['published']))
                or row['metadata_status'] not in ('indexed-from-public-metadata','cited-by-local-reference','indexed-from-secondary-directory')):
            return ['invalid curated metadata status or publication date']
        if row['metadata_status'] == 'indexed-from-secondary-directory' and not row.get('metadata_evidence'):
            return ['secondary metadata requires provenance']
    return []


CLAIM_STATES = {'project-analysis', 'independently-verified', 'needs-review', 'disputed', 'deprecated'}


def check_claims(claims, allowed_sources):
    """Validate evidence shape, not reviewer identity or mathematical validity."""
    if not isinstance(claims, list):
        return ['claims must be an array']
    seen, errors = set(), []
    required = {'claim_id','statement','status','assumptions','evidence'}
    optional = {'derivation','counterexample','reviewer','reviewed_at','verification','status_reason'}
    for claim in claims:
        if not isinstance(claim, dict) or required - claim.keys() or claim.keys() - required - optional:
            errors.append('Malformed claim')
            continue
        key = claim['claim_id']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key) or key in seen:
            errors.append('Invalid or duplicate claim ID')
            continue
        seen.add(key)
        status = claim['status']
        if not isinstance(status, str) or status not in CLAIM_STATES:
            errors.append(key + ': invalid claim state')
            continue
        if not isinstance(claim['statement'],str) or not claim['statement'].strip() or not isinstance(claim['assumptions'],list) or any(not isinstance(a,str) or not a.strip() for a in claim['assumptions']):
            errors.append(key + ': missing statement or invalid assumptions')
        evidence = claim['evidence']
        if (not isinstance(evidence, list) or not evidence or any(not isinstance(e, dict) or set(e) != {'source','location'}
                or not isinstance(e['source'], str) or e['source'] not in allowed_sources
                or not isinstance(e['location'], str) or not e['location'].strip() for e in evidence)):
            errors.append(key + ': missing or untraceable claim evidence')
        def text(field):
            return isinstance(claim.get(field), str) and bool(claim[field].strip())
        if status in {'project-analysis','independently-verified'} and not text('derivation'):
            errors.append(key + ': missing independent derivation')
        if status in {'needs-review','disputed','deprecated'} and not text('status_reason'):
            errors.append(key + ': missing state rationale')
        if status == 'independently-verified':
            from datetime import date
            if not all(text(k) for k in ('reviewer', 'reviewed_at', 'verification')):
                errors.append(key + ': independent verification requires reviewer, date and reproducible method')
            else:
                try:
                    date.fromisoformat(claim['reviewed_at'])
                except ValueError:
                    errors.append(key + ': invalid verification date')
        elif {'reviewer','reviewed_at','verification'} & claim.keys():
            errors.append(key + ': verification metadata does not match state')
    return errors
