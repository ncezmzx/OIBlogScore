"""Git inventory, durable state, and confined filesystem operations."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import contextmanager


def git(root, *args, check=True):
    return subprocess.run(['git', '-C', str(root), '--literal-pathspecs', *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Repo:
    def __init__(self, path):
        self.root = Path(os.fsdecode(git(path, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n')))
        self.state = self.path('.oiblogscore')
        if git(self.root, 'ls-files', '-z', '--', '.oiblogscore').stdout:
            raise ValueError('Reserved state path .oiblogscore is tracked; move tracked files before use')
        self.config = self.load(self.path('oiblogscore.json'), {})

    def path(self, name):
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or '.git' in rel.parts:
            raise ValueError('Unsafe path: ' + str(name))
        p = self.root
        for part in rel.parts:
            p = p / part
            if p.is_symlink():
                raise ValueError('Symlinks are unsupported: ' + str(name))
        return p

    @staticmethod
    def load(path, default):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

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
        result = git(self.root, 'diff', '--no-renames', '--name-only', '-z', base, 'HEAD', '--', check=False)
        return set(os.fsdecode(result.stdout).split('\0')) - {''} if base and result.returncode == 0 else set()

    def dirty(self, name):
        if git(self.root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--', name).stdout:
            return True
        indexed = git(self.root, 'show', ':' + name, check=False)
        return indexed.returncode != 0 or indexed.stdout != self.path(name).read_bytes()
