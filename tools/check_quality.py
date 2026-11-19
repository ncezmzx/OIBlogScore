#!/usr/bin/env python3
"""Offline quality gate for this repository's Markdown/frontmatter conventions."""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

from catalog_quality import check_sources
from catalog import ROOT as CATALOG, load, normalize


ROOT = CATALOG.parents[1]
SKILLS = set('oi-' + n for n in (
    'blog-review proof-review complexity-review code-review counterexample blog-score'
    ' repository-audit blog-repair repair-verify').split())
TOPIC_SECTIONS = '问题模型 算法原理 成立条件 关键不变量 证明路线 复杂度推导 错误与反例 性质边界 审稿检查 区别与联系 依据'.split()
WORKFLOW_SECTIONS = '输入规格 工作流与资源 输出规格 失败处理 验证过程 示例'.split()
PROTOCOL_SECTIONS = {
    'oi-proof-review/references/protocol.md': (
        'Definitions and Preconditions', 'Lemma Dependency', 'Forward Implication', 'Reverse Implication'),
    'oi-proof-review/references/methods.md': (
        'Induction', 'Invariants', 'Exchange Arguments', 'Greedy Correctness', 'DP Correctness',
        'Graph Algorithm Correctness', 'Data Structure Invariants'),
    'oi-proof-review/references/cost-and-witness.md': (
        'Amortized Analysis', 'Probabilistic Analysis', 'Counterexample Construction'),
    'oi-complexity-review/references/protocol.md': (
        'Recurrence Analysis', 'Divide and Conquer Complexity', 'CDQ Complexity', '整体二分与多层结构'),
    'oi-complexity-review/references/accounting.md': (
        'Amortized Complexity', 'Potential Method', 'Aggregate Analysis', 'Expected Complexity', 'Randomized Algorithms'),
    'oi-complexity-review/references/resources.md': (
        'Graph Algorithm Complexity', 'Segment Tree Operation Counting', 'Data Structure Complexity', 'Memory Complexity'),
    'oi-code-review/references/cpp-semantics.md': (
        'Integer Overflow', 'Signed/Unsigned Conversion', 'Undefined Behavior', 'Array Bounds',
        'Iterator Invalidation', 'Reference and Pointer Lifetime'),
    'oi-code-review/references/cpp-implementation.md': (
        'Recursion Depth', 'Memory Allocation', 'Lazy Propagation', 'Persistent Data Structures',
        'Fast I/O', 'Time Complexity Pitfalls'),
}
CATEGORIES = {'data-structures', 'divide-and-conquer', 'dp', 'graph', 'mathematics', 'strings'}
LINK = re.compile(r'\[[^\]\n]*\]\((\S+?)\)|^ {0,3}\[[^\]\n]+\]:\s*(\S+)', re.M)
FENCES = re.compile(r'^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$', re.M | re.S)
HEADINGS = re.compile(r'^#{1,6}\s+(.+?)\s*#*$', re.M)
SECTIONS = re.compile(r'^## (.+)$', re.M)


def sections(text):
    parts = SECTIONS.split(text)
    return dict(zip(parts[1::2], parts[2::2]))


def anchors(text):
    counts, names = Counter(), set()
    for value in HEADINGS.findall(FENCES.sub('', text)):
        slug = re.sub(r'[^\w -]', '', value.lower()).replace(' ', '-')
        count = counts[slug]
        counts[slug] += 1
        names.add(slug if count == 0 else f'{slug}-{count}')
    return names


def read(path):
    return path.read_text(encoding='utf-8')


def markdown_links(text):
    # Repository convention: one destination without literal whitespace, no
    # nested delimiters. Code examples are not interpreted as references.
    clean = re.sub(r'`[^`\n]+`', '', FENCES.sub('', text))
    for match in LINK.finditer(clean):
        yield next(item for item in match.groups() if item).strip('<>')


def check(root):
    issues = []
    catalog = root / 'resources' / 'algorithm-catalog'
    skills = root / 'skills'
    skill_folders = {p.name for p in skills.iterdir() if p.is_dir() and not p.name.startswith('.')}
    if skill_folders != SKILLS:
        issues.append('Wrong skill set: ' + ', '.join(sorted(skill_folders ^ SKILLS)))
    trees = [root / 'docs', root / 'resources', skills, root / 'examples']
    files = {p for tree in trees for p in tree.rglob('*.md')} | set(root.glob('*.md'))
    edges = {}
    for path in sorted(files):
        text = read(path)
        if not any(ch.isalnum() for line in text.splitlines() if not line.lstrip().startswith('#') for ch in line):
            issues.append(f'{path}: empty knowledge text')
        edges[path] = set()
        boundary = next((folder for folder in path.parents if folder.parent == skills), root)
        for raw in markdown_links(text):
            url = urlsplit(raw)
            if url.scheme or url.netloc:
                continue  # Offline gate: validates local links, not source availability.
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target != boundary and boundary not in target.parents:
                issues.append(f'{path}: link outside its package: {raw}')
                continue
            if target.is_dir():
                target = target / 'README.md'
            if not target.is_file():
                issues.append(f'{path}: dangling link: {raw}')
            elif url.fragment and target.suffix == '.md' and unquote(url.fragment) not in anchors(read(target)):
                issues.append(f'{path}: missing heading: {raw}')
            else:
                edges[path].add(target)

    def reachable(start):
        seen, pending = set(), [start]
        while pending:
            item = pending.pop()
            if item not in seen:
                seen.add(item)
                pending.extend(edges.get(item, set()) - seen)
        return seen

    def require_sections(path, names, minimum):
        if not path.is_file():
            issues.append(f'{path}: missing required document')
            return {}
        text = read(path)
        for heading, count in Counter(SECTIONS.findall(text)).items():
            if count > 1:
                issues.append(f'{path}: duplicate section {heading}')
        body = sections(text)
        for name in names:
            if sum(ch.isalnum() for ch in body.get(name, '')) < minimum:
                issues.append(f'{path}: missing or insubstantial section {name}')
        return body

    for name in sorted(SKILLS & skill_folders):
        directory = skills / name
        path = directory / 'SKILL.md'
        text = read(path) if path.is_file() else ''
        # Local lint convention intentionally accepts only the simple, valid
        # YAML subset we author: unquoted scalar name, description, license.
        meta = re.match(r'\A---\nname: ([a-z0-9]+(?:-[a-z0-9]+)*)\ndescription: ([^\n]+)\n(?:license: MIT\n)?---\n', text)
        if (not meta or meta[1] != name or len(name) > 64 or not 1 <= len(meta[2].strip()) <= 1024
                or meta[2].lstrip()[0] in '!&*{}[],#|>@`"\'' or ': ' in meta[2] or ' #' in meta[2]):
            issues.append(f'{path}: invalid Agent Skills metadata or unsupported local YAML style')
        if name not in {'oi-blog-repair', 'oi-repair-verify'} and ('Catalog 检索' not in sections(text) or 'python tools/catalog.py' not in text or 'refs <id>' not in text):
            issues.append(f'{path}: missing Catalog workflow and provenance lookup')
        if '工作流' not in sections(text):
            issues.append(f'{path}: missing workflow entry point')
        require_sections(directory / 'references' / 'workflow.md', WORKFLOW_SECTIONS, 12)
        package_files = {p for p in directory.rglob('*') if p.suffix in ('.md', '.json', '.py')}
        for target in sorted(package_files - reachable(path)):
            issues.append(f'{target}: unreachable from its Skill entry')

    for relative, names in PROTOCOL_SECTIONS.items():
        require_sections(skills / relative, names, 35)

    index = load(catalog)
    if index['version'] != 1 or set(index['categories']) != CATEGORIES:
        issues.append('Wrong catalog version or categories')
    ids, paths, aliases, bodies, per_category = set(), set(), {}, {}, Counter()
    for item in index['topics']:
        key, cat, rel = item['id'], item['category'], item['path']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key) or key in ids or rel in paths:
            issues.append(f'{key}: invalid/duplicate catalog id or path')
        ids.add(key)
        paths.add(rel)
        if cat not in CATEGORIES or rel != f'{cat}/{key}.md':
            issues.append(f'{key}: inconsistent path/category')
            continue
        per_category[cat] += 1
        path = catalog / rel
        if path.is_file() and not read(path).startswith('# ' + item['title'] + '\n'):
            issues.append(f'{key}: title does not match index')
        if not item['aliases']:
            issues.append(f'{key}: missing search aliases')
        for value in [key, *item['aliases']]:
            norm = normalize(value)
            if not norm or norm in aliases and aliases[norm] != key:
                issues.append(f'{key}: empty or ambiguous alias {value}')
            aliases[norm] = key
        if path not in edges.get(catalog / cat / 'README.md', set()):
            issues.append(f'{key}: missing category link')
        body = require_sections(path, TOPIC_SECTIONS, 22)
        if body and not re.search(r'\]\(https://', body.get('依据', '')):
            issues.append(f'{key}: missing source citation')
        for section in TOPIC_SECTIONS[:-1]:
            content = re.sub(r'\s+', '', body.get(section, ''))
            if not content:
                continue
            if content in bodies:
                issues.append(f'{key}:{section}: duplicates {bodies[content]}')
            bodies[content] = f'{key}:{section}'
    actual = {p.relative_to(catalog).as_posix() for p in catalog.rglob('*.md') if p.name != 'README.md'}
    if actual != paths:
        issues.append('Catalog index/file mismatch: ' + ', '.join(sorted(actual ^ paths)))
    for path in sorted(set(catalog.rglob('*.md')) - reachable(catalog / 'README.md')):
        issues.append(f'{path}: not reachable from catalog index')
    for category in sorted(CATEGORIES):
        if per_category[category] == 0:
            issues.append(f'{category}: category has no topics')
    issues.extend(check_sources(catalog))
    return issues, per_category


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        issues, counts = check(args.root.resolve())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Invalid repository structure: ' + str(exc), file=sys.stderr)
        return 1
    for issue in issues:
        print(issue, file=sys.stderr)
    if not issues:
        print(f'{len(SKILLS)} skills; {sum(counts.values())} topics across {len(counts)} categories; quality gate passed')
    return int(bool(issues))


if __name__ == '__main__':
    sys.exit(main())
