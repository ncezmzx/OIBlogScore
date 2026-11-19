"""Fingerprint deterministic review inputs, including an optional external policy checkout."""
import json
import os
from pathlib import Path

from ..repository import digest


def rule_fingerprint(repo, files, hash_file):
    runtime = Path(__file__).resolve().parents[1]
    rule_items = [(p.relative_to(runtime).as_posix(), digest(p.read_bytes()))
                  for p in sorted(runtime.rglob('*')) if p.is_file() and p.suffix in {'.py', '.json'}]
    for rule in repo.config.get('rule_paths', ['skills', 'resources']):
        repo.path(rule)
        rule_items.extend((n, hash_file(n)) for n in sorted(files) if n == rule or n.startswith(rule.rstrip('/') + '/'))
    external = os.environ.get('OIBLOGSCORE_REFERENCE_ROOT')
    extra = []
    if external:
        root = Path(external).expanduser().resolve()
        for dirname in ('skills', 'resources'):
            folder = root / dirname
            if not folder.is_dir() or folder.is_symlink():
                raise ValueError('Invalid external reference folder: ' + str(folder))
            for current, dirs, filenames in os.walk(folder):
                dirs[:] = sorted(d for d in dirs if not (Path(current) / d).is_symlink() and not d.startswith('.') and d != '__pycache__')
                for name in sorted(filenames):
                    path = Path(current) / name
                    if not path.is_symlink() and path.is_file() and path.suffix in {'.md', '.json', '.py', '.txt', '.yaml', '.yml', '.toml'}:
                        extra.append((path.relative_to(root).as_posix(), digest(path.read_bytes())))
    return digest(json.dumps([rule_items, extra, repo.config], sort_keys=True).encode())
