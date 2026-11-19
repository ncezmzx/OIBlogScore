"""Audit result contract and persistence. This does not judge evidence semantics."""
import json

from ..repository import stamp

DIMENSIONS = ('algorithm', 'proof', 'complexity', 'code', 'counterexample', 'language')
VERDICTS = ('PASS', 'SUSPECTED', 'FAIL', 'NOT_CHECKED', 'NOT_APPLICABLE')
SEVERITIES = ('Critical', 'Major', 'Minor', 'Suggestion')


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
