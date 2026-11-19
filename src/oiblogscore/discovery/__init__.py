"""Conservative discovery: retain ambiguous candidates and explain classification."""
import fnmatch
import json
import os
import posixpath
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from ..repository import digest, git, stamp

ARTICLES = {'.md', '.markdown', '.mdx', '.tex', '.latex', '.html', '.htm'}
CODE = {'.cpp', '.cc', '.cxx', '.c', '.hpp', '.h', '.py', '.java', '.rs', '.go', '.pas', '.js', '.ts'}
CATEGORIES = {
    'dp': r'动态规划|\bdp\b', 'graph': r'图论|最短路|dijkstra|拓扑|最小生成树',
    'greedy': r'贪心|greedy', 'strings': r'字符串|kmp|后缀数组',
    'number-theory': r'数论|gcd|欧几里得|同余', 'data-structures': r'线段树|树状数组|并查集',
    'search': r'二分|回溯|\bdfs\b|\bbfs\b', 'flow': r'网络流|dinic|最大流',
    'geometry': r'计算几何|凸包|叉积', 'counting': r'组合数学|容斥|计数',
}
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


def discover(repo):
    names = {os.fsdecode(p) for p in git(repo.root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').stdout.split(b'\0') if p}
    files, exclusions, issues = set(), [], []
    for name in sorted(names):
        if name.startswith('.oiblogscore/'):
            continue
        try:
            if repo.path(name).is_file():
                files.add(name)
        except ValueError as exc:
            issues.append({'path': name, 'reason': str(exc)})
    hashes, references = {}, {}
    configured = repo.config.get('dependencies', {})

    def content(name):
        return repo.path(name).read_bytes()

    def hash_file(name):
        if name not in hashes:
            hashes[name] = digest(content(name))
        return hashes[name]

    def edges(name):
        if name not in references:
            suffix = PurePosixPath(name).suffix.lower()
            refs, unresolved = links(content(name).decode('utf-8', errors='replace'), name, files) if suffix in ARTICLES | CODE else (set(), set())
            for dep in configured.get(name, []):
                (refs if dep in files else unresolved).add(dep)
            references[name] = refs, unresolved
        return references[name]

    # Include runtime code and review policy contents, not just a timestamp.
    rule_items = [digest(p.read_bytes()) for p in sorted(Path(__file__).resolve().parents[1].rglob('*')) if p.suffix in {'.py', '.json'}]
    for rule in repo.config.get('rule_paths', ['skills', 'resources']):
        repo.path(rule)
        rule_items.extend((n, hash_file(n)) for n in sorted(files) if n == rule or n.startswith(rule.rstrip('/') + '/'))
    rules = digest(json.dumps([rule_items, repo.config], sort_keys=True).encode())
    articles = {}
    for name in sorted(files):
        path = PurePosixPath(name)
        suffix = path.suffix.lower()
        if suffix not in ARTICLES:
            continue
        pattern = next((p for p in repo.config.get('exclude', []) if fnmatch.fnmatchcase(name, p) or name.startswith(p.rstrip('/') + '/')), None)
        if pattern:
            exclusions.append({'path': name, 'reason': 'excluded by ' + pattern})
            continue
        raw = content(name)
        text = raw.decode('utf-8', errors='replace')
        enc_ok = raw == text.encode('utf-8')
        header = re.match(r'\A(?:\ufeff)?---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
        meta = header[1] if header else ''
        author = re.search(r'^author:[ \t]*([^\r\n]+)', meta, re.M)
        if suffix in {'.tex', '.latex'} and not author:
            author = re.search(r'\\author\{([^{}]+)\}', text)
        identity = author[1].strip().strip('\'"') if author else None
        if identity and (identity[0] in '[{>|' or '\\and' in identity):
            identity = None
        parts = {p.lower() for p in path.parts[:-1]}
        categories = [key for key, regex in CATEGORIES.items() if re.search(regex, text, re.I)]
        kind, reason = 'candidate', 'supported text format; article role uncertain'
        if re.search(r'^draft:\s*true\s*$', meta, re.M | re.I) or parts & {'drafts', '_drafts'}:
            kind, reason = 'draft', 'draft metadata or directory'
        elif parts & {'archive', 'archives', 'archived'}:
            kind, reason = 'archive', 'archive directory'
        elif path.stem.lower() == 'readme' or parts & {'docs', 'documentation'}:
            kind, reason = 'documentation', 'README name or documentation directory'
        elif parts & {'dist', '_site', 'build', 'public'} or re.search(r'<!--[^>]*generated', text, re.I):
            kind, reason = 'possibly-generated', 'output directory or generated marker'
        elif meta or categories or parts & {'blog', 'posts', '_posts'}:
            kind, reason = 'article', 'front matter, algorithm keywords or blog directory'
        if not enc_ok:
            issues.append({'path': name, 'reason': 'not UTF-8; Agent must resolve encoding'})
        deps, queue, missing = set(), [name], set()
        seen = {name}
        while queue:
            current = queue.pop()
            refs, broken = edges(current)
            missing.update((current, ref) for ref in broken)
            for dep in refs - seen:
                deps.add(dep)
                seen.add(dep)
                queue.append(dep)
        # Undeclared shared code can be added explicitly in config.
        inputs = {p: hash_file(p) for p in sorted(deps | {name})}
        fingerprint = digest(json.dumps([inputs, sorted(missing), rules], sort_keys=True).encode())
        articles[name] = dict(path=name, type=suffix[1:], author=identity, kind=kind, reason=reason,
                              categories=categories, content_hash=inputs[name], inputs=inputs,
                              fingerprint=fingerprint, code=sorted(d for d in deps if PurePosixPath(d).suffix.lower() in CODE),
                              resources=sorted(d for d in deps if PurePosixPath(d).suffix.lower() not in CODE),
                              unresolved_dependencies=[list(item) for item in sorted(missing)])
    return dict(repository=repo.text_git('remote', 'get-url', 'origin'), branch=repo.text_git('branch', '--show-current'),
                commit=repo.text_git('rev-parse', '--verify', 'HEAD'), scanned_at=stamp(), rules=rules,
                articles=articles, exclusions=exclusions, discovery_issues=issues)
