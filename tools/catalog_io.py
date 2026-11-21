"""Strict JSON, duplicate-aware indexing and portable catalog paths."""
import json
from pathlib import PureWindowsPath


def read(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f'{path}: duplicate JSON key {key}')
            obj[key] = value
        return obj

    def reject_constant(value):
        raise ValueError(f'{path}: non-JSON constant {value}')

    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=reject_constant)


def unique_rows(rows, label):
    if not isinstance(rows, list):
        raise ValueError(f'{label}: expected an array')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'].strip():
            raise ValueError(f'{label}: invalid record ID')
        key = row['id']
        if key in result:
            raise ValueError(f'{label}: duplicate ID {key}')
        result[key] = row
    return result


def local_path(root, relative):
    if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
            or any(ord(ch) < 32 for ch in relative) or PureWindowsPath(relative).drive):
        raise ValueError(f'Unsafe catalog path: {relative!r}')
    parts = relative.split('/')
    if any(p in ('', '.', '..') or p.endswith(('.', ' ')) or PureWindowsPath(p).is_reserved() for p in parts):
        raise ValueError(f'Unsafe catalog path: {relative!r}')
    root = root.resolve(strict=True)
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink() or target.resolve().parent != target.parent:
            raise ValueError(f'Catalog path is a link or escapes root: {relative}')
    return target
