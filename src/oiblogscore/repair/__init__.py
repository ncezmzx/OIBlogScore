"""Minimal prose edits, write-ahead journal, exact verification and rollback."""
from collections import Counter
import difflib
import re
import uuid

from ..repository import atomic, digest, stamp
from ..verification import candidates, verify_pair


def read_text(path):
    return path.read_bytes().decode('utf-8')


def style_profile(text):
    text = re.sub(r'\A---\r?\n.*?\r?\n---(?:\r?\n|$)|```.*?```|`[^`\n]+`|\$[^$\n]+\$', '', text, flags=re.S)
    ps = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    sentences = [s.strip() for s in re.split(r'[。！？!?\n]|\.(?=\s|$)', text) if s.strip()]
    vocab = re.findall(r'\b[A-Za-z][A-Za-z0-9_+]*\b|动态规划|线段树|贪心|最短路|复杂度', text)
    phrases = Counter(re.findall(r'就(?:是|行|好)|其实|然后|比如|不妨|我觉得|先.+?再', text))
    mean = sum(map(len, sentences)) / max(1, len(sentences))
    return dict(mean_sentence_chars=mean, mean_paragraph_chars=sum(map(len, ps)) / max(1, len(ps)),
                first_person=len(re.findall(r'我(?:们)?|\bI\b|\bwe\b', text)), vocabulary=Counter(vocab).most_common(15),
                punctuation=dict(Counter(re.findall(r'[，。！？：；、,.!?;:]', text))),
                mixing=dict(spaced=len(re.findall(r'[\u4e00-\u9fff] +[A-Za-z]|[A-Za-z] +[\u4e00-\u9fff]', text)),
                            adjacent=len(re.findall(r'[\u4e00-\u9fff][A-Za-z]|[A-Za-z][\u4e00-\u9fff]', text))),
                sentence_openers=Counter(s[:4] for s in sentences).most_common(10), phrases=phrases.most_common(10),
                colloquial_markers=len(re.findall(r'嘛|啦|吧|咱|这儿|挺|咋', text)), concise_proxy=bool(sentences) and mean < 35)


def diff(name, before, after):
    changes = difflib.unified_diff(before.splitlines(True), after.splitlines(True), 'a/' + name, 'b/' + name)
    return ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in changes)


def reconstruct(entry):
    lines = entry['before'].splitlines(keepends=True)
    for edit in entry['edits']:
        if edit['active']:
            lines[edit['line'] - 1] = edit['after']
    return ''.join(lines)


def reconcile(repo, journal):
    for entry in journal:
        pending = entry.get('pending')
        if pending is None:
            continue
        actual = digest(repo.path(entry['path']).read_bytes())
        if actual == pending['new_hash']:
            entry.update(pending['update'])
        elif actual != pending['old_hash']:
            raise ValueError('Interrupted write conflicts with current file: ' + entry['path'])
        entry.pop('pending')
        repo.save('repairs.json', journal)


def transition(repo, journal, entry, before, after, update, require_clean=False):
    p = repo.path(entry['path'])
    if (require_clean and repo.dirty(entry['path'])) or read_text(p) != before:
        raise ValueError('File changed or is dirty: ' + entry['path'])
    entry['pending'] = dict(old_hash=digest(before.encode()), new_hash=digest(after.encode()), update=update)
    repo.save('repairs.json', journal)
    if (require_clean and repo.dirty(entry['path'])) or read_text(repo.path(entry['path'])) != before:
        entry.pop('pending')
        repo.save('repairs.json', journal)
        raise ValueError('File changed before write: ' + entry['path'])
    atomic(p, after.encode())
    reconcile(repo, journal)


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
            outcomes.append({'path': name, 'status': 'dirty (skipped)'})
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


def rollback(repo, name, edit_id=None):
    journal = repo.read('repairs.json', [])
    reconcile(repo, journal)
    entry = next((e for e in reversed(journal) if e['path'] == name and e['status'] == 'applied'), None)
    if not entry:
        raise ValueError('No active repair for ' + name)
    before = reconstruct(entry)
    edits = [dict(edit, active=False) if not edit_id or edit['id'] == edit_id else edit for edit in entry['edits']]
    if edits == entry['edits']:
        raise ValueError('Unknown or inactive edit ID')
    after = reconstruct(dict(entry, edits=edits))
    # The working file must match the journal byte-for-byte. Reject staged edits.
    from ..repository import git
    if git(repo.root, 'diff', '--cached', '--name-only', '-z', '--', name).stdout:
        raise ValueError('Cannot roll back a staged file')
    status = 'rolled_back' if after == entry['before'] else 'applied'
    if status == 'applied' and verify_pair(entry['before'], after):
        raise ValueError('Remaining edits no longer verify')
    transition(repo, journal, entry, before, after, dict(edits=edits, status=status, rolled_back_at=stamp(),
                                                       diff=diff(name, entry['before'], after), verification='PASS'))
    return diff(name, before, after)


def verify_journal(repo):
    journal = repo.read('repairs.json', [])
    results = []
    for entry in journal:
        if entry['status'] != 'applied' and 'pending' not in entry:
            continue
        expected = reconstruct(entry)
        errors = verify_pair(entry['before'], expected)
        try:
            if read_text(repo.path(entry['path'])) != expected:
                errors.append('current file differs from journal; re-review needed')
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        if 'pending' in entry:
            errors.append('interrupted transaction; reconcile before verification')
        results.append({'id': entry['id'], 'path': entry['path'], 'errors': errors})
    return results
