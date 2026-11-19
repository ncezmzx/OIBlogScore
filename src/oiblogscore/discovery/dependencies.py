"""Repository-local reference parsing and transitive dependency walks."""
import posixpath
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

ARTICLES = {'.md', '.markdown', '.mdx', '.tex', '.latex', '.html', '.htm'}
CODE = {'.cpp', '.cc', '.cxx', '.c', '.hpp', '.h', '.py', '.java', '.rs', '.go', '.pas', '.js', '.ts'}

REFERENCES = re.compile(
    r'''\]\(\s*(?:<([^>]+)>|([^\s)]+))|^\s{0,3}\[[^\]\n]+\]:\s*(\S+)|(?:href|src)\s*=\s*["']([^"']+)|\\(?:input|include|includegraphics|lstinputlisting)(?:\[[^\]]*\])?\{([^}]+)\}|(?:from|import)\s*["'](\.[^"']+)["']|^\s*#\s*include\s*"([^"]+)"''',
    re.M | re.I)


def links(text, name, files):
    found, missing = set(), set()
    for match in REFERENCES.finditer(text):
        raw = next(x for x in match.groups() if x is not None).strip('<>')
        try:
            url = urlsplit(raw)
        except ValueError:
            continue
        if url.scheme or url.netloc or not url.path:
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path))) if not url.path.startswith('/') else posixpath.normpath(unquote(url.path).lstrip('/'))
        options = [target, target + '.tex', target + '.js', target + '.mdx', target + '/index.md']
        existing = next((item for item in options if item in files), None)
        if existing and existing != name:
            found.add(existing)
        elif not existing:
            missing.add(raw)
    return found, missing


class DependencyGraph:
    """Memoized adjacency over one Git-visible file inventory."""

    def __init__(self, files, content, configured):
        self.files = files
        self.content = content
        self.configured = configured
        self.cache = {}

    def edges(self, name):
        if name not in self.cache:
            suffix = PurePosixPath(name).suffix.lower()
            refs, missing = set(), set()
            if suffix in ARTICLES | CODE:
                refs, missing = links(self.content(name).decode('utf-8', errors='replace'), name, self.files)
            for dep in self.configured.get(name, []):
                (refs if dep in self.files else missing).add(dep)
            self.cache[name] = refs, missing
        return self.cache[name]

    def closure(self, name):
        seen, queue, missing = {name}, [name], set()
        while queue:
            current = queue.pop()
            refs, broken = self.edges(current)
            missing.update((current, ref) for ref in broken)
            new = refs - seen
            seen.update(new)
            queue.extend(new)
        return seen - {name}, missing
