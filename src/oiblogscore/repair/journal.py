"""Write-ahead repair transactions, conflict detection, verification and rollback."""
from ..repository import atomic, digest, git, stamp
from ..verification import verify_pair
from .diff import diff


def read_text(path):
    return path.read_bytes().decode('utf-8')


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
