"""Conservative discovery: retain ambiguous candidates and explain classification."""
import fnmatch
import json
import os
import re
from pathlib import PurePosixPath

from ..repository import digest, git, stamp
from .dependencies import ARTICLES, CODE, DependencyGraph
from .manifest import rule_fingerprint

CATEGORIES = {
    'dp': r'动态规划|\bdp\b', 'graph': r'图论|最短路|dijkstra|拓扑|最小生成树',
    'greedy': r'贪心|greedy', 'strings': r'字符串|kmp|后缀数组',
    'number-theory': r'数论|gcd|欧几里得|同余', 'data-structures': r'线段树|树状数组|并查集',
    'search': r'二分|回溯|\bdfs\b|\bbfs\b', 'flow': r'网络流|dinic|最大流',
    'geometry': r'计算几何|凸包|叉积', 'counting': r'组合数学|容斥|计数',
}
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
    hashes, texts = {}, {}

    def content(name):
        if name in texts:
            return texts[name]
        raw = repo.path(name).read_bytes()
        hashes[name] = digest(raw)
        if PurePosixPath(name).suffix.lower() in ARTICLES | CODE:
            texts[name] = raw
        return raw

    def hash_file(name):
        if name not in hashes:
            content(name)
        return hashes[name]

    graph = DependencyGraph(files, content, repo.config.get('dependencies', {}),
                            repo.config.get('dependency_resolutions', {}))

    rules = rule_fingerprint(repo, files, hash_file)
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
        deps, missing, edges = graph.closure(name)
        # Undeclared shared code can be added explicitly in config.
        inputs = {p: hash_file(p) for p in sorted(deps | {name})}
        fingerprint = digest(json.dumps([inputs, sorted(missing), rules], sort_keys=True).encode())
        articles[name] = dict(path=name, type=suffix[1:], author=identity, kind=kind, reason=reason,
                              categories=categories, content_hash=inputs[name], inputs=inputs,
                              fingerprint=fingerprint, code=sorted(d for d in deps if PurePosixPath(d).suffix.lower() in CODE),
                              resources=sorted(d for d in deps if PurePosixPath(d).suffix.lower() not in CODE),
                              dependency_edges=edges, unresolved_dependencies=[list(item) for item in sorted(missing)])
    # Check bytes, not size or timestamps. This detects persistent changes to
    # observed inputs, not ABA changes or a simultaneous multi-file snapshot.
    for name, expected in hashes.items():
        if digest(repo.path(name).read_bytes()) != expected:
            raise ValueError('File changed during discovery; rerun: ' + name)
    return dict(snapshot_consistency='revalidated', repository=repo.text_git('remote', 'get-url', 'origin'), branch=repo.text_git('branch', '--show-current'),
                commit=repo.text_git('rev-parse', '--verify', 'HEAD'), scanned_at=stamp(), rules=rules,
                articles=articles, exclusions=exclusions, discovery_issues=issues)
