"""Git inventory, durable state, and confined filesystem operations."""
import errno
import hashlib
import json
import ntpath
import os
import re
import stat
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
import unicodedata
import uuid
from contextlib import contextmanager


RESERVED_STATE = '.oiblogscore'


def folded_name(name):
    """Portable identity used to refuse case/normalization collisions."""
    return unicodedata.normalize('NFC', name).casefold()


def reserved_name(part):
    checker = getattr(ntpath, 'isreserved', None)
    return checker(part) if checker is not None else PureWindowsPath(part).is_reserved()


def sync_directory(parent):
    """Best-effort POSIX durability for a rename; unsupported filesystems are ignored."""
    if os.name == 'nt':
        return
    try:
        fd = os.open(str(parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


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
    if os.name == 'nt' and path.exists() and not os.access(str(path), os.W_OK):
        raise PermissionError(errno.EACCES, 'Target is read-only', str(path))
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(tmp, path)
        # Apply the old permissions after the rename so a read-only target
        # cannot leave a read-only temporary file behind on Windows.
        if mode is not None:
            try:
                os.chmod(path, mode)
            except OSError:
                pass
        sync_directory(path.parent)
    finally:
        if os.path.exists(tmp):
            try:
                os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass


class Repo:
    def __init__(self, path):
        self.root = Path(os.fsdecode(git(path, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n'))).resolve(strict=True)
        tracked = [os.fsdecode(item) for item in git(self.root, 'ls-files', '-z').stdout.split(b'\0') if item]
        for name in tracked:
            first = name.split('/', 1)[0]
            if first == RESERVED_STATE or folded_name(first) == RESERVED_STATE:
                raise ValueError('Reserved state path or variant is tracked; move tracked files before use: ' + name)
        for entry in os.listdir(self.root):
            if entry != RESERVED_STATE and folded_name(entry) == RESERVED_STATE:
                raise ValueError('Reserved state path variant exists; rename it before use: ' + entry)
        self.state = self.path(RESERVED_STATE)
        raw_file_mode = git(self.root, 'config', '--bool', 'core.fileMode', check=False)
        self.file_mode = raw_file_mode.returncode != 0 or raw_file_mode.stdout.strip() != b'false'
        raw_autocrlf = git(self.root, 'config', '--get', 'core.autocrlf', check=False)
        self.autocrlf = os.fsdecode(raw_autocrlf.stdout).strip() if raw_autocrlf.returncode == 0 else ''
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
        if (rel.is_absolute() or PureWindowsPath(name).drive or PureWindowsPath(name).root
                or '\\' in str(name) or ':' in str(name)
                or any(part.lower() in ('..', '.git') or part.endswith(('.', ' '))
                       or reserved_name(part) for part in rel.parts)):
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
        token = uuid.uuid4().hex
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('{} {}\n'.format(os.getpid(), token))
                f.flush()
                os.fsync(f.fileno())
            yield
        finally:
            # Never delete a lock that another process re-created after ours
            # was removed; compare the ownership token before unlinking.
            try:
                current = p.read_text(encoding='ascii', errors='replace')
            except OSError:
                current = None
            if current is not None and token in current:
                try:
                    p.unlink()
                except OSError:
                    pass

    def text_git(self, *args):
        return self._git(*args).strip()

    def _git(self, *args):
        return os.fsdecode(git(self.root, *args, check=False).stdout)

    def changed(self, base):
        if not base:
            return set()
        if not isinstance(base, str) or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', base):
            raise ValueError('Invalid cached audit base commit')
        exists = git(self.root, 'rev-parse', '--verify', '--quiet', base + '^{commit}', check=False)
        if exists.returncode != 0:
            raise ValueError('Cached audit base commit is unavailable; run a full audit')
        result = git(self.root, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-only', '-z', base, 'HEAD', '--', check=False)
        if result.returncode != 0:
            raise ValueError('Cannot compare cached audit base; run a full audit')
        return set(os.fsdecode(result.stdout).split('\0')) - {''}

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

    def dirty_detail(self, name):
        indexed = self.clean_index_entry(name)
        if indexed is None:
            return {'reason': 'not a clean stage-0 regular file'}
        mode, oid = indexed
        path = self.path(name)
        if not path.is_file():
            return {'reason': 'not a regular file'}
        if self.file_mode and os.name != 'nt' and bool(path.stat().st_mode & stat.S_IXUSR) != (mode == b'100755'):
            return {'reason': 'executable bit differs'}
        blob = git(self.root, 'cat-file', 'blob', oid.decode('ascii'))
        if blob.stdout == path.read_bytes():
            return None
        hints = []
        if self.autocrlf in ('true', 'input'):
            hints.append('core.autocrlf=' + self.autocrlf)
        attrs = git(self.root, 'check-attr', 'text', 'eol', '--', name, check=False)
        if attrs.returncode == 0:
            for line in attrs.stdout.decode('utf-8', 'replace').splitlines():
                parts = line.rsplit(': ', 2)
                if len(parts) == 3 and parts[1] in ('text', 'eol') and parts[2] != 'unspecified':
                    hints.append('Git attribute ' + parts[1] + '=' + parts[2])
        return {'reason': 'worktree bytes differ from HEAD', 'filters': hints}

    def dirty(self, name):
        return self.dirty_detail(name) is not None
