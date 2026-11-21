"""Repository reports never count stale or pending results as reviewed."""
from collections import Counter
from html import escape
import json
import re
import unicodedata

from ..audit import DIMENSIONS, PENDING, SEVERITIES, VERDICTS, load_state
from ..repair import verify_journal
from ..repository import digest


def build(repo, manifest):
    state = load_state(repo)
    changed = repo.changed(state['commit'])
    journal = repo.read('repairs.json', [])
    verified = verify_journal(repo, journal)
    authority = {name: digest(json.dumps(value, sort_keys=True).encode('ascii'))
                 for name, value in (('audit.json', state), ('repairs.json', journal))}
    verdicts, severity = Counter(), Counter()
    reviewed = 0
    unresolved = list(manifest['discovery_issues'])
    manifest = dict(manifest, articles={name: dict(item) for name, item in manifest["articles"].items()})
    for name, article in manifest['articles'].items():
        results = {}
        for dim in DIMENSIONS:
            task = state['tasks'].get(name, {}).get(dim, {})
            result = task.get('result') if task.get('fingerprint') == article['fingerprint'] and not changed.intersection(article['inputs']) else None
            results[dim] = result or {'verdict': 'NOT_CHECKED', 'evidence': 'No current Agent result', 'findings': []}
            verdict = results[dim]['verdict']
            verdicts[verdict] += 1
            for finding in results[dim]['findings']:
                severity[finding['severity']] += 1
                unresolved.append(dict(finding, path=name, dimension=dim))
            if verdict in PENDING | {'SUSPECTED'} and not results[dim]['findings']:
                unresolved.append(dict(path=name, dimension=dim, reason=results[dim]['evidence']))
        done = not article['unresolved_dependencies'] and all(result['verdict'] not in PENDING for result in results.values())
        reviewed += done
        edits = [edit for e in journal if e['path'] == name and e['status'] == 'applied' for edit in e['edits'] if edit['active']]
        language = results['language']['findings']
        article.update(results=results, audit_status='REVIEWED' if done else 'PENDING',
                       last_reviewed_at=max((r.get('reviewed_at', '') for r in results.values()), default='') or None,
                       repair_status=('UNVERIFIED' if any(v['path'] == name and v['errors'] for v in verified) else 'VERIFIED' if edits else 'NOT_MODIFIED'),
                       language_issues=len(language), automatic_edits=len(edits),
                       awaiting_confirmation=sum(f.get('repair_class') in ('B', 'D') for f in language))
        unresolved.extend(dict(path=name, dependency_from=src, reference=ref, reason='unresolved local reference') for src, ref in article['unresolved_dependencies'])
    unresolved.extend(dict(path=item['path'], reason=error) for item in verified for error in item['errors'])
    count = len(manifest['articles'])
    all_verified = not any(item['errors'] for item in verified)
    # 'Discovered' means the configured Git-visible scope was enumerated.
    discovery_ok = not manifest['discovery_issues'] and not any(
        a['unresolved_dependencies'] for a in manifest['articles'].values())
    if count == 0:
        unresolved.append(dict(path='.', reason='No candidate articles discovered in the configured scope'))
    return dict(manifest, authority_sha256=authority, discovered=count, reviewed=reviewed, unreviewed=count-reviewed,
                repaired=len({e['path'] for e in journal if e['status'] == 'applied'}),
                completion=dict(discovery=discovery_ok, audit=count > 0 and reviewed == count, verification=all_verified),
                status='COMPLETE' if discovery_ok and count > 0 and reviewed == count and all_verified else 'INCOMPLETE',
                verdicts={key: verdicts[key] for key in VERDICTS}, severity={key: severity[key] for key in SEVERITIES},
                repairs=[{key: value for key, value in entry.items() if key not in ('before', 'pending')} for entry in journal],
                verification=verified, repair_run=repo.read('repair-run.json', []), unresolved=unresolved)


def inline(text):
    """Render repository-controlled data as text, not links, HTML or terminal controls."""
    line = ''.join(c if unicodedata.category(c) not in {'Cc', 'Cf'} else f'\\u{ord(c):04x}' for c in str(text))
    return re.sub(r'([\\`*_{}\[\]()#!|~])', r'\\\1', escape(line, quote=False))


def markdown(report):
    lines = ['# OIBlogScore Repository Report', '', '**{}** · {} · `{}`'.format(report['status'], inline(report['branch']), report['commit']),
             '', 'Repository: ' + inline(report['repository']), 'Scanned: ' + report['scanned_at'], '',
             'Discovered: {discovered} · Reviewed: {reviewed} · Unreviewed: {unreviewed} · Repaired: {repaired}'.format(**report),
             '', 'Completion: ' + ', '.join('{}={}'.format(k, v) for k, v in report['completion'].items()),
             'Verdicts: ' + ', '.join('{}={}'.format(k, v) for k, v in report['verdicts'].items()),
             'Severity: ' + ', '.join('{}={}'.format(k, v) for k, v in report['severity'].items()), '', '## Articles', '']
    for name, item in report['articles'].items():
        lines.append('- {}: {} | {} | language={} / edits={} / confirm={}'.format(inline(name), item['kind'],
                     ', '.join('{}: {}'.format(k, v['verdict']) for k, v in item['results'].items()),
                     item['language_issues'], item['automatic_edits'], item['awaiting_confirmation']))
    lines += ['', '## Repairs', '']
    for entry in report['repairs']:
        lines.append('- {}: {} ({})'.format(inline(entry['path']), entry['status'], entry.get('verification', 'pending')))
    lines += ['', '## Unresolved', '']
    for item in report['unresolved']:
        location = ':'.join(inline(item[key]) for key in ('path', 'dimension', 'location') if key in item)
        detail = item.get('message', item.get('reason', ''))
        if 'reference' in item:
            detail += ' (' + item['dependency_from'] + ': ' + item['reference'] + ')'
        lines.append('- {}: {}'.format(location, inline(detail)))
        if 'evidence' in item:
            lines.append('  - Evidence: ' + inline(item['evidence']))
    lines += ['', 'See report.json for findings, evidence, per-edit reasons, exact diffs and verification details.']
    return '\n'.join(lines) + '\n'
