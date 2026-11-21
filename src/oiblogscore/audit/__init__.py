"""A persistent queue of independent, evidence-bearing Agent review tasks."""
import uuid


from .results import DIMENSIONS, PENDING, SEVERITIES, VERDICTS, load_state, submit


def fresh(article):
    return {'ticket': uuid.uuid4().hex, 'fingerprint': article['fingerprint']}


def schedule(repo, manifest, mode='incremental', paths=(), types=(), categories=(), dimensions=DIMENSIONS):
    state = load_state(repo)
    changed = repo.changed(state['commit'])
    if mode == 'resume':
        paths, types, categories, dimensions = state.get('scope', [[], [], [], list(DIMENSIONS)])
    dimensions = tuple(dict.fromkeys(dimensions))
    if not dimensions or set(dimensions) - set(DIMENSIONS):
        raise ValueError('Invalid audit dimensions')
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
            if item.get('result', {}).get('verdict', 'NOT_CHECKED') in PENDING:
                work.append(dict(path=name, dimension=dim, ticket=item['ticket'], fingerprint=item['fingerprint'], inputs=article['inputs'], dependency_edges=article['dependency_edges'], unresolved_dependencies=article['unresolved_dependencies']))
    state['commit'] = manifest['commit']
    repo.save('audit.json', state)
    repo.save('queue.json', {'root': str(repo.root), 'tasks': work})
    return work
