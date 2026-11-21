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

    def resolve(raw):
        try:
            url = urlsplit(raw)
        except ValueError:
            missing.add(raw)
            return
        if url.scheme or url.netloc or not url.path:
            return
        raw_path = unquote(url.path)
        target = (posixpath.normpath(raw_path.lstrip('/')) if raw_path.startswith('/') else
                  posixpath.normpath(posixpath.join(posixpath.dirname(name), raw_path)))
        if target in files:
            if target != name:
                found.add(target)
            return
        options = (target + '.tex', target + '.js', target + '.mdx', target + '.md', target + '/index.md')
        candidates = [item for item in options if item in files]
        if len(candidates) == 1:
            if candidates[0] != name:
                found.add(candidates[0])
        else:
            missing.add(raw)

    for match in REFERENCES.finditer(text):
        resolve(next(x for x in match.groups() if x is not None).strip('<>'))
    for match in re.finditer(r'\b(?:import|require)\s*\(([^)\n]*)\)|\{%\s*(?:include|include_relative)\s+([^%\n]*)%\}', text):
        expression = match[1]
        if expression is not None:
            literal = re.fullmatch(r"\s*(['\"])([^'\"]+)\1\s*", expression)
            if literal:
                if literal[2].startswith(('.', '/')):
                    resolve(literal[2])
                continue  # bare module specifier, not known to resolve in this repository
        missing.add(match[0])  # dynamic/template syntax: do not infer the runtime target
    return found, missing


class DependencyGraph:
    """Memoized adjacency over one Git-visible file inventory."""

    def __init__(self, files, content, configured, resolutions):
        self.files = files
        self.content = content
        self.configured = configured
        self.resolutions = resolutions
        self.cache = {}

    def edges(self, name):
        if name not in self.cache:
            suffix = PurePosixPath(name).suffix.lower()
            refs, missing = set(), set()
            if suffix in ARTICLES | CODE:
                refs, missing = links(self.content(name).decode('utf-8', errors='replace'), name, self.files)
            explicit = set(self.configured.get(name, []))
            for ref, targets in self.resolutions.get(name, {}).items():
                if ref in missing and all(target in self.files for target in targets):
                    missing.remove(ref)
                    explicit.update(targets)
            for dep in explicit:
                (refs if dep in self.files else missing).add(dep)
            self.cache[name] = refs, missing, explicit
        return self.cache[name]

    def closure(self, name):
        seen, queue, missing, edges = {name}, [name], set(), []
        while queue:
            current = queue.pop()
            refs, broken, explicit = self.edges(current)
            edges.extend(dict(source=current, target=ref, kind='configured' if ref in explicit else 'heuristic')
                         for ref in sorted(refs))
            missing.update((current, ref) for ref in broken)
            new = refs - seen
            seen.update(new)
            queue.extend(new)
        return seen - {name}, missing, sorted(edges, key=lambda edge: (edge['source'], edge['target']))
