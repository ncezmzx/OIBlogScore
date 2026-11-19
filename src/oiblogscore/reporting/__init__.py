"""Repository reports never count stale or pending results as reviewed."""
from collections import Counter

from ..audit import DIMENSIONS, SEVERITIES, VERDICTS
from ..repair import verify_journal


def build(repo, manifest):
    state = repo.read('audit.json', {'tasks': {}, 'commit': ''})
    changed = repo.changed(state['commit'])
    journal = repo.read('repairs.json', [])
    verified = verify_journal(repo)
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
            if verdict in ('NOT_CHECKED', 'SUSPECTED') and not results[dim]['findings']:
                unresolved.append(dict(path=name, dimension=dim, reason=results[dim]['evidence']))
        done = all(result['verdict'] != 'NOT_CHECKED' for result in results.values())
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
    discovery_ok = not manifest['discovery_issues']
    return dict(manifest, discovered=count, reviewed=reviewed, unreviewed=count-reviewed,
                repaired=len({e['path'] for e in journal if e['status'] == 'applied'}),
                completion=dict(discovery=discovery_ok, audit=reviewed == count, verification=all_verified),
                status='COMPLETE' if discovery_ok and reviewed == count and all_verified else 'INCOMPLETE',
                verdicts={key: verdicts[key] for key in VERDICTS}, severity={key: severity[key] for key in SEVERITIES},
                repairs=[{key: value for key, value in entry.items() if key not in ('before', 'pending')} for entry in journal],
                verification=verified, repair_run=repo.read('repair-run.json', []), unresolved=unresolved)


def markdown(report):
    lines = ['# OIBlogScore Repository Report', '', '**{}** · {} · `{}`'.format(report['status'], report['branch'], report['commit']),
             '', 'Repository: ' + report['repository'], 'Scanned: ' + report['scanned_at'], '',
             'Discovered: {discovered} · Reviewed: {reviewed} · Unreviewed: {unreviewed} · Repaired: {repaired}'.format(**report),
             '', 'Completion: ' + ', '.join('{}={}'.format(k, v) for k, v in report['completion'].items()),
             'Verdicts: ' + ', '.join('{}={}'.format(k, v) for k, v in report['verdicts'].items()),
             'Severity: ' + ', '.join('{}={}'.format(k, v) for k, v in report['severity'].items()), '', '## Articles', '']
    for name, item in report['articles'].items():
        lines.append('- {}: {} | {} | language={} / edits={} / confirm={}'.format(name.replace('\n', '\\n'), item['kind'],
                     ', '.join('{}: {}'.format(k, v['verdict']) for k, v in item['results'].items()),
                     item['language_issues'], item['automatic_edits'], item['awaiting_confirmation']))
    lines += ['', '## Repairs', '']
    for entry in report['repairs']:
        lines.append('- {}: {} ({})'.format(entry['path'], entry['status'], entry.get('verification', 'pending')))
    lines += ['', '## Unresolved', '']
    lines.extend('- {}: {}'.format(f['path'], f.get('message', f.get('reason', ''))) for f in report['unresolved'])
    lines += ['', 'See report.json for findings, evidence, per-edit reasons, exact diffs and verification details.']
    return '\n'.join(lines) + '\n'
