"""Git inventory, durable state, and confined filesystem operations."""
import hashlib
import json
import os
import re
import stat
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
from contextlib import contextmanager


def git(root, *args, check=True):
    return subprocess.run(['git', '--no-replace-objects', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                           '-C', str(root), '--literal-pathspecs', *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def atomic(path, data, before_replace=None):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            if path.exists():
                os.chmod(tmp, path.stat().st_mode & 0o777)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Repo:
    def __init__(self, path):
        self.root = Path(os.fsdecode(git(path, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n'))).resolve(strict=True)
        self.state = self.path('.oiblogscore')
        if git(self.root, 'ls-files', '-z', '--', '.oiblogscore').stdout:
            raise ValueError('Reserved state path .oiblogscore is tracked; move tracked files before use')
        self.config = self.load(self.path('oiblogscore.json'), {})
        if not isinstance(self.config, dict):
            raise ValueError('oiblogscore.json must be an object')
        def strings(value):
            return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
        for key in ('exclude', 'rule_paths'):
            if key in self.config and not strings(self.config[key]):
                raise ValueError(key + ' must be an array of nonempty strings')
        deps = self.config.get('dependencies', {})
        if not isinstance(deps, dict) or any(not strings(v) for v in deps.values()):
            raise ValueError('dependencies must map paths to arrays of paths')
        for article, refs in deps.items():
            for name in (article, *refs):
                self.path(name)
        resolutions = self.config.get('dependency_resolutions', {})
        if not isinstance(resolutions, dict):
            raise ValueError('dependency_resolutions must map paths to objects')
        for name, refs in resolutions.items():
            self.path(name)
            if not isinstance(refs, dict) or any(not k.strip() or not strings(v) for k, v in refs.items()):
                raise ValueError('dependency_resolutions must map reference text to arrays of paths')
            for paths in refs.values():
                for target in paths:
                    self.path(target)

    def path(self, name):
        rel = Path(name)
        if (rel.is_absolute() or PureWindowsPath(name).drive or '\\' in str(name) or ':' in str(name)
                or any(part.lower() in ('..', '.git') or part.endswith(('.', ' '))
                       or PureWindowsPath(part).is_reserved() for part in rel.parts)):
            raise ValueError('Unsafe path: ' + str(name))
        p = self.root
        for part in rel.parts:
            p = p / part
            if p.is_symlink() or p.resolve() != p:
                raise ValueError('Symlinks are unsupported: ' + str(name))
        return p

    @staticmethod
    def load(path, default):
        if not path.exists():
            return default
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError(f'{path}: duplicate JSON key {key}')
                obj[key] = value
            return obj
        def reject(value):
            raise ValueError(f'{path}: invalid JSON constant {value}')
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=reject)

    def read(self, name, default):
        return self.load(self.path('.oiblogscore/' + name), default)

    def save(self, name, value):
        self.state.mkdir(exist_ok=True)
        atomic(self.path('.oiblogscore/' + name), json.dumps(value, ensure_ascii=False, indent=2).encode())

    @contextmanager
    def lock(self):
        self.state.mkdir(exist_ok=True)
        p = self.path('.oiblogscore/lock')
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('State locked; after a crash remove the lock only once no process is running')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(str(os.getpid()))
            yield
        finally:
            p.unlink()

    def text_git(self, *args):
        return self._git(*args).strip()

    def _git(self, *args):
        return os.fsdecode(git(self.root, *args, check=False).stdout)

    def changed(self, base):
        if not base:
            return set()
        if not isinstance(base, str) or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', base):
            raise ValueError('Invalid cached audit base commit')
        result = git(self.root, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z', base, 'HEAD', '--', check=False)
        return set(os.fsdecode(result.stdout).split('\0')) - {''} if base and result.returncode == 0 else set()

    def clean_index_entry(self, name):
        """Match regular HEAD and stage-0 entries without running status/clean filters."""
        indexed = git(self.root, 'ls-files', '--stage', '-z', '--', name).stdout.split(b'\0')
        if len(indexed) != 2 or b'\t' not in indexed[0]:
            return None
        header, index_path = indexed[0].split(b'\t', 1)
        mode, oid, stage = header.split()
        if stage != b'0' or mode not in (b'100644', b'100755') or index_path != os.fsencode(name):
            return None
        head = git(self.root, 'ls-tree', '-z', 'HEAD', '--', name, check=False)
        expected = b' '.join((mode, b'blob', oid)) + b'\t' + index_path + b'\0'
        return (mode, oid) if head.returncode == 0 and head.stdout == expected else None

    def dirty(self, name):
        indexed = self.clean_index_entry(name)
        if indexed is None:
            return True
        mode, oid = indexed
        path = self.path(name)
        if not path.is_file() or (os.name != 'nt' and bool(path.stat().st_mode & stat.S_IXUSR) != (mode == b'100755')):
            return True
        blob = git(self.root, 'cat-file', 'blob', oid.decode('ascii'))
        return blob.stdout != path.read_bytes()
