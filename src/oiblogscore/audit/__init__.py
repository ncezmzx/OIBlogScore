"""A persistent queue of independent, evidence-bearing Agent review tasks."""
import json
import uuid

from ..repository import stamp

DIMENSIONS = ('algorithm', 'proof', 'complexity', 'code', 'counterexample', 'language')
VERDICTS = ('PASS', 'SUSPECTED', 'FAIL', 'NOT_CHECKED', 'NOT_APPLICABLE')
SEVERITIES = ('Critical', 'Major', 'Minor', 'Suggestion')


def fresh(article):
    return {'ticket': uuid.uuid4().hex, 'fingerprint': article['fingerprint']}


def schedule(repo, manifest, mode='incremental', paths=(), types=(), categories=(), dimensions=DIMENSIONS):
    state = repo.read('audit.json', {'tasks': {}, 'commit': ''})
    changed = repo.changed(state['commit'])
    if mode == 'resume':
        paths, types, categories, dimensions = state.get('scope', [[], [], [], list(DIMENSIONS)])
    state['scope'] = [list(paths), list(types), list(categories), list(dimensions)]
    tasks, work = state['tasks'], []
    for name in list(tasks):
        if name not in manifest['articles']:
            del tasks[name]
    for name, article in manifest['articles'].items():
        record = tasks.setdefault(name, {})
        for dim in list(record):
            if record[dim]['fingerprint'] != article['fingerprint'] or changed.intersection(article['inputs']):
                del record[dim]
        if paths and not any(p in {'.', ''} or name == p or name.startswith(p + '/') for p in paths):
            continue
        if types and article['type'] not in types:
            continue
        if categories and not set(categories).intersection(article['categories']):
            continue
        for dim in dimensions:
            if mode == 'full' or dim not in record:
                record[dim] = fresh(article)
            item = record[dim]
            if item.get('result', {}).get('verdict', 'NOT_CHECKED') == 'NOT_CHECKED':
                work.append(dict(path=name, dimension=dim, ticket=item['ticket'], fingerprint=item['fingerprint'], inputs=article['inputs'], unresolved_dependencies=article['unresolved_dependencies']))
    state['commit'] = manifest['commit']
    repo.save('audit.json', state)
    repo.save('queue.json', {'root': str(repo.root), 'tasks': work})
    return work


def submit(repo, manifest, result_path):
    result = json.loads(result_path.read_text(encoding='utf-8'))
    state = repo.read('audit.json', {'tasks': {}})
    name, dim = result['path'], result['dimension']
    article = manifest['articles'].get(name)
    task = state['tasks'].get(name, {}).get(dim)
    if (not article or not task or dim not in DIMENSIONS
            or any(result[key] != task[key] for key in ('ticket', 'fingerprint'))
            or task['fingerprint'] != article['fingerprint']
            or repo.changed(state.get('commit')).intersection(article['inputs'])):
        raise ValueError('Stale or unknown task; regenerate the queue')
    if task.get('result', {}).get('verdict', 'NOT_CHECKED') != 'NOT_CHECKED':
        raise ValueError('Task already finalized; start a full targeted audit to replace it')
    if result['verdict'] not in VERDICTS or not isinstance(result['evidence'], str) or not result['evidence'].strip():
        raise ValueError('Verdict and written evidence/rationale required')
    findings = result.get('findings', [])
    if not isinstance(findings, list) or any(not isinstance(f, dict) or f.get('severity') not in SEVERITIES or any(not isinstance(f.get(k), str) or not f[k].strip() for k in ('location', 'message', 'evidence')) for f in findings):
        raise ValueError('Findings require severity, location, message and evidence')
    if result['verdict'] in ('FAIL', 'SUSPECTED') and not findings:
        raise ValueError('FAIL and SUSPECTED require at least one finding')
    if result['verdict'] in ('PASS', 'NOT_APPLICABLE') and any(f['severity'] in ('Critical', 'Major') for f in findings):
        raise ValueError('PASS/NOT_APPLICABLE conflicts with a Critical/Major finding')
    if dim == 'language' and any(f.get('repair_class') not in ('A', 'B', 'C', 'D') for f in findings):
        raise ValueError('Language findings require repair_class A/B/C/D')
    task['result'] = dict(result, findings=findings, reviewed_at=stamp())
    repo.save('audit.json', state)
