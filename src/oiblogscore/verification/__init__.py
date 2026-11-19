"""Fail-closed exact verification of a tiny subset of Markdown prose edits."""
import json
import re
from pathlib import Path

RULES = json.loads((Path(__file__).resolve().parents[1] / 'rules.json').read_text(encoding='utf-8'))


def candidates(text):
    # Deliberately reject entire documents with opaque containers or uncommon
    # math/markup. No parser means no claim of general Markdown support.
    lines = text.splitlines(keepends=True)
    start = 0
    if lines and lines[0].rstrip('\r\n') == '---':
        end = next((i for i in range(1, len(lines)) if lines[i].rstrip('\r\n') == '---'), None)
        if end is None:
            return {}
        start = end + 1
    body = ''.join(lines[start:])
    if any(token in body for token in ('<', '\\', '\x00', '\ufeff', '$$', '{{', '{%', ':::', '~~~', '\x85', '\u2028', '\u2029', '\v', '\f')):
        return {}
    fence = None
    eligible = {}
    for i in range(start, len(lines)):
        line = lines[i].rstrip('\r\n')
        match = re.match(r'^ {0,3}(`{3,})(.*)$', line)
        if match:
            if fence is None:
                fence = len(match[1])
            elif len(match[1]) >= fence and not match[2].strip():
                fence = None
            continue
        if fence is not None or any(c in line for c in ('`', '$')):
            if fence is None:  # May span lines or use a nonstandard inline extension.
                if line.count('`') % 2 or line.count('$') % 2:
                    return {}
            continue
        if line in RULES and i > 0 and not lines[i-1].strip() and (i+1 == len(lines) or not lines[i+1].strip()):
            eligible[i] = RULES[line]
    return eligible if fence is None else {}


def verify_pair(before, after):
    if before == after:
        return ['no change']
    a, b = before.splitlines(keepends=True), after.splitlines(keepends=True)
    if len(a) != len(b):
        return ['line count changed']
    eligible = candidates(before)
    failures = []
    for i, (left, right) in enumerate(zip(a, b)):
        if left != right:
            eol = left[len(left.rstrip('\r\n')):]
            if i not in eligible or right != eligible[i] + eol:
                failures.append('line {}: not an approved exact prose edit'.format(i + 1))
    return failures
