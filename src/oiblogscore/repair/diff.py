"""Unified diff rendering without normalizing source line endings."""
import difflib


def diff(name, before, after):
    changes = difflib.unified_diff(before.splitlines(True), after.splitlines(True), 'a/' + name, 'b/' + name)
    return ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in changes)
