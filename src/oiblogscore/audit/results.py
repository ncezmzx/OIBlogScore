"""Audit result contract and persistence. This does not judge evidence semantics."""
import re

from ..repository import stamp

DIMENSIONS = ('algorithm', 'proof', 'complexity', 'code', 'counterexample', 'language')
VERDICTS = ('PASS', 'SUSPECTED', 'FAIL', 'NOT_CHECKED', 'NEEDS_CONTEXT', 'NOT_APPLICABLE')
PENDING = frozenset({'NOT_CHECKED', 'NEEDS_CONTEXT'})
SEVERITIES = ('Critical', 'Major', 'Minor', 'Suggestion')


def validate_result(result, dim):
    if not isinstance(result, dict):
        raise ValueError('Audit result must be an object')
    if result.get('verdict') not in VERDICTS or not isinstance(result.get('evidence'), str) or not result['evidence'].strip():
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
    return findings


def load_state(repo):
    state = repo.read('audit.json', {'tasks': {}, 'commit': ''})
    if not isinstance(state, dict) or not isinstance(state.get('tasks'), dict) or not isinstance(state.get('commit'), str):
        raise ValueError('Malformed audit state; preserve audit.json and inspect before restarting')
    scope = state.get('scope', [[], [], [], list(DIMENSIONS)])
    if (not isinstance(scope, list) or len(scope) != 4
            or any(not isinstance(v, list) or any(not isinstance(item, str) for item in v) for v in scope)
            or not scope[3] or len(scope[3]) != len(set(scope[3])) or set(scope[3]) - set(DIMENSIONS)):
        raise ValueError('Malformed audit scope')
    for name, record in state['tasks'].items():
        if not isinstance(record, dict) or record.keys() - set(DIMENSIONS):
            raise ValueError('Malformed cached task record: ' + name)
        for dim, task in record.items():
            if (not isinstance(task, dict) or not isinstance(task.get('ticket'), str)
                    or not re.fullmatch('[0-9a-f]{32}', task['ticket'])
                    or not isinstance(task.get('fingerprint'), str) or not re.fullmatch('[0-9a-f]{64}', task['fingerprint'])):
                raise ValueError('Malformed cached task: ' + name + ':' + dim)
            if 'result' in task:
                validate_result(task['result'], dim)
                if any(task['result'].get(key) != value for key, value in
                       (('path', name), ('dimension', dim), ('ticket', task['ticket']), ('fingerprint', task['fingerprint']))):
                    raise ValueError('Cached result does not match its task: ' + name + ':' + dim)
    return state


def submit(repo, manifest, result_path):
    result = repo.load(result_path, None)
    if not isinstance(result, dict):
        raise ValueError('Submission must be a JSON object')
    state = load_state(repo)
    name, dim = result['path'], result['dimension']
    article = manifest['articles'].get(name)
    task = state['tasks'].get(name, {}).get(dim)
    if (not article or not task or dim not in DIMENSIONS
            or any(result[key] != task[key] for key in ('ticket', 'fingerprint'))
            or task['fingerprint'] != article['fingerprint']
            or repo.changed(state.get('commit')).intersection(article['inputs'])):
        raise ValueError('Stale or unknown task; regenerate the queue')
    if task.get('result', {}).get('verdict', 'NOT_CHECKED') not in PENDING:
        raise ValueError('Task already finalized; start a full targeted audit to replace it')
    findings = validate_result(result, dim)
    task['result'] = dict(result, findings=findings, reviewed_at=stamp())
    repo.save('audit.json', state)
