"""Minimal prose edits, write-ahead journal, exact verification and rollback."""
import uuid

from ..repository import digest, stamp
from ..verification import candidates, verify_pair
from .diff import diff
from .journal import read_text, reconcile, rollback, transition, verify_journal
from .style import style_profile


def repair(repo, manifest, mode, paths=()):
    journal = repo.read('repairs.json', [])
    reconcile(repo, journal)
    profiles, outcomes = {}, []
    authors = {}
    for name, article in manifest['articles'].items():
        if article['author']:
            authors.setdefault(article['author'], []).append(name)
    active = {entry['path'] for entry in journal if entry['status'] == 'applied'}
    for name, article in manifest['articles'].items():
        if paths and not any(name == p or name.startswith(p + '/') or p in ('', '.') for p in paths):
            continue
        if article['type'] not in ('md', 'markdown'):
            continue
        try:
            before = read_text(repo.path(name))
        except UnicodeDecodeError:
            outcomes.append({'path': name, 'status': 'not utf-8 (skipped)'})
            continue
        if digest(before.encode()) != article['content_hash']:
            outcomes.append({'path': name, 'status': 'input changed'})
            continue
        identity = article['author']
        peers = []
        for peer in authors.get(identity, []):
            if peer != name:
                other = manifest['articles'][peer]
                try:
                    source = read_text(repo.path(peer))
                except UnicodeDecodeError:
                    continue
                if digest(source.encode()) == other['content_hash']:
                    peers.append((peer, source))
        profiles[name] = dict(self=style_profile(before), sources=[p for p, _ in peers],
                              same_author=style_profile('\n\n'.join(t for _, t in peers)) if peers else None)
        if name in active:
            outcomes.append({'path': name, 'status': 'active journal (skipped)'})
            continue
        if repo.dirty(name):
            detail = repo.dirty_detail(name) or {'reason': 'unclean worktree'}
            message = detail['reason']
            if detail.get('filters'):
                message += '; Git may normalize line endings or attributes: ' + ', '.join(detail['filters'])
            outcomes.append({'path': name, 'status': 'dirty (skipped)', 'detail': message})
            continue
        lines = before.splitlines(keepends=True)
        edits = []
        for i, replacement in candidates(before).items():
            old = lines[i]
            lines[i] = replacement + old[len(old.rstrip('\r\n')):]
            edits.append(dict(id=uuid.uuid4().hex, line=i+1, before=old, after=lines[i],
                              reason='Curated standalone editorial phrase correction (class A)', active=True))
        if not edits:
            continue
        after = ''.join(lines)
        failures = verify_pair(before, after)
        patch = diff(name, before, after)
        if failures:
            outcomes.append(dict(path=name, status='rejected', reasons=failures, diff=patch))
            continue
        print(patch, end='')
        if mode == 'interactive' and input('Accept verified edits to this file? [y/N] ').strip().lower() != 'y':
            outcomes.append(dict(path=name, status='declined', diff=patch))
            continue
        entry = dict(id=uuid.uuid4().hex, path=name, before=before, edits=[], created_at=stamp(), status='planned')
        journal.append(entry)
        transition(repo, journal, entry, before, after, dict(edits=edits, status='applied', diff=patch, verification='PASS'), require_clean=True)
        outcomes.append(dict(path=name, status='applied', id=entry['id']))
    repo.save('style.json', profiles)
    repo.save('repair-run.json', outcomes)
    return outcomes
