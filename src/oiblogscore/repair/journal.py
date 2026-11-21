"""Write-ahead repair transactions, conflict detection, verification and rollback."""
from ..repository import atomic, digest, git, stamp
from ..verification import verify_pair
from .diff import diff


def read_text(path):
    return path.read_bytes().decode('utf-8')


def reconstruct(entry):
    if not isinstance(entry, dict) or not isinstance(entry.get('before'), str) or not isinstance(entry.get('edits'), list):
        raise ValueError('Malformed repair journal entry')
    lines = entry['before'].splitlines(keepends=True)
    used_ids, used_lines = set(), set()
    for edit in entry['edits']:
        if (not isinstance(edit, dict) or not isinstance(edit.get('id'), str) or edit['id'] in used_ids
                or type(edit.get('line')) is not int or not 1 <= edit['line'] <= len(lines)
                or edit['line'] in used_lines or type(edit.get('active')) is not bool
                or not isinstance(edit.get('after'), str) or edit.get('before') != lines[edit['line'] - 1]):
            raise ValueError('Malformed or inconsistent repair edit in journal')
        used_ids.add(edit['id'])
        used_lines.add(edit['line'])
        if edit['active']:
            lines[edit['line'] - 1] = edit['after']
    return ''.join(lines)


def reconcile(repo, journal):
    for entry in journal:
        pending = entry.get('pending')
        if pending is None:
            continue
        update = pending['update']
        if (not isinstance(update, dict) or update.keys() - {'edits','status','diff','verification','rolled_back_at'}
                or update.get('status') not in ('applied', 'rolled_back')
                or digest(reconstruct(entry).encode()) != pending['old_hash']):
            raise ValueError('Malformed interrupted repair: ' + entry['path'])
        updated = dict(entry, **update)
        updated_text = reconstruct(updated)
        if (digest(updated_text.encode()) != pending['new_hash']
                or (updated['status'] == 'applied' and verify_pair(entry['before'], updated_text))
                or (updated['status'] == 'rolled_back' and updated_text != entry['before'])):
            raise ValueError('Invalid interrupted repair contents: ' + entry['path'])
        actual = digest(repo.path(entry['path']).read_bytes())
        if actual == pending['new_hash']:
            entry.update(update)
        elif actual != pending['old_hash']:
            raise ValueError('Interrupted write conflicts with current file: ' + entry['path'])
        elif entry['status'] == 'planned':
            entry['status'] = 'aborted'
        entry.pop('pending')
        repo.save('repairs.json', journal)


def transition(repo, journal, entry, before, after, update, require_clean=False, require_unstaged=False):
    p = repo.path(entry['path'])
    def conflict():
        name = entry['path']
        target = repo.path(name)
        if not target.is_file() or target.stat().st_nlink != 1:
            raise ValueError('Repair target is not a singly-linked regular file: ' + name)
        if require_unstaged:
            indexed = repo.clean_index_entry(name)
            if indexed is None:
                raise ValueError('Cannot roll back a staged file')
            if git(repo.root, 'cat-file', 'blob', indexed[1].decode('ascii')).stdout != entry['before'].encode():
                raise ValueError('Cannot roll back: HEAD no longer matches the original article')
        return (require_clean and repo.dirty(name)) or read_text(target) != before

    if conflict():
        raise ValueError('File changed or is dirty: ' + entry['path'])
    entry['pending'] = dict(old_hash=digest(before.encode()), new_hash=digest(after.encode()), update=update)
    repo.save('repairs.json', journal)
    def guard():
        if conflict():
            raise ValueError('File changed before write; reconcile journal: ' + entry['path'])

    atomic(p, after.encode(), before_replace=guard)
    reconcile(repo, journal)


def rollback(repo, name, edit_id=None):
    journal = repo.read('repairs.json', [])
    reconcile(repo, journal)
    entry = next((e for e in reversed(journal) if e['path'] == name and e['status'] == 'applied'), None)
    if not entry:
        raise ValueError('No active repair for ' + name)
    before = reconstruct(entry)
    if repo.path(name).suffix.lower() not in ('.md', '.markdown') or verify_pair(entry['before'], before):
        raise ValueError('Journal does not describe a verified prose repair')
    edits = [dict(edit, active=False) if not edit_id or edit['id'] == edit_id else edit for edit in entry['edits']]
    if edits == entry['edits']:
        raise ValueError('Unknown or inactive edit ID')
    after = reconstruct(dict(entry, edits=edits))
    # The working file must match the journal byte-for-byte. Reject staged edits.
    status = 'rolled_back' if after == entry['before'] else 'applied'
    if status == 'applied' and verify_pair(entry['before'], after):
        raise ValueError('Remaining edits no longer verify')
    transition(repo, journal, entry, before, after, dict(edits=edits, status=status, rolled_back_at=stamp(),
                                                       diff=diff(name, entry['before'], after), verification='PASS'), require_unstaged=True)
    return diff(name, before, after)


def verify_journal(repo, journal=None):
    if journal is None:
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
