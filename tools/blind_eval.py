#!/usr/bin/env python3
"""Export blinded case prompts and compare two independently collected Agent runs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import sys

from catalog_data import ROOT, build, read
from console import utf8_stdio
from target_grading import aggregate

FIXTURE = ROOT.parents[1] / 'tests/fixtures/blind'
VERDICTS = {'PASS', 'FAIL', 'NOT_CHECKED'}
FIELDS = {'id', 'verdict', 'reason', 'source_ids', 'upstream_verified'}


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_sha(root, names):
    root = Path(root)
    digest = hashlib.sha256()
    for name in names:
        base = root / name
        if not base.exists():
            continue
        paths = [base] if base.is_file() else sorted(
            path for path in base.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
        for path in paths:
            digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def source_head(root):
    run = subprocess.run(['git', '--no-optional-locks', '-C', str(root), 'rev-parse', '--verify', 'HEAD'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return run.stdout.decode('ascii', 'ignore').strip() if run.returncode == 0 else None


def instruction(condition):
    access = ('Use the catalog when relevant; cite source IDs and state whether you independently verified the claim.'
              if condition == 'catalog' else 'Do not access the Catalog, references, or external tools. Use reasoning from the excerpt.')
    return (access + ' Return one row per case with id, verdict (PASS, FAIL or NOT_CHECKED), reason, source_ids, '
            'and upstream_verified (true only if claiming upstream content itself is verified).')


def manifest(condition, seed, text):
    root = ROOT.parents[1]
    return {'condition': condition, 'seed': seed,
            'cases_sha256': file_sha(FIXTURE / 'cases.json'),
            'instruction_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'catalog_sha256': tree_sha(root, ['resources/algorithm-catalog']),
            'tooling_sha256': tree_sha(root, ['tools', 'skills', 'src']),
            'source_head': source_head(root)}


def pack(condition, seed=None):
    text = instruction(condition)
    cases = read(FIXTURE / 'cases.json')
    if seed is not None:
        random.Random(seed).shuffle(cases)
    return {'condition': condition, 'seed': seed, 'instruction': text,
            'manifest': manifest(condition, seed, text), 'cases': cases}


def prepare(condition, destination, seed=None, repo=None):
    repo = Path(repo or ROOT.parents[1]).resolve()
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Destination already exists; choose a fresh directory')
    if destination.resolve() == repo or repo in destination.resolve().parents:
        raise ValueError('Destination must be outside the OIBlogScore checkout')
    cases = read(FIXTURE / 'cases.json')
    if seed is not None:
        random.Random(seed).shuffle(cases)
    text = instruction(condition)
    destination.mkdir(parents=True)
    (destination / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / 'instruction.txt').write_text(text + '\n', encoding='utf-8')
    if condition == 'catalog':
        shutil.copytree(repo, destination / 'repo', ignore=shutil.ignore_patterns(
            '.git', '.oiblogscore', '__pycache__', '*.pyc', 'tests', 'build', '*.egg-info'))
    for name in ('key.json', 'targets.json'):
        if any(destination.rglob(name)):
            raise ValueError('Sanitized bundle contains a private answer file: ' + name)
    record = manifest(condition, seed, text)
    (destination / 'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'condition': condition, 'destination': str(destination), 'manifest': record}


def validate_key(key, cases, data):
    ids = [row['id'] for row in cases]
    if len(ids) != len(set(ids)) or set(ids) != key.keys():
        raise ValueError('Blind cases and keys must correspond one-to-one')
    for case, row in key.items():
        if (row['verdict'] not in VERDICTS or row['dimension'] not in {'algorithm', 'proof', 'complexity', 'code'}
                or not row['basis'].strip() or (row['algorithm'] is not None and row['algorithm'] not in data['algorithms'])):
            raise ValueError('Invalid private answer key: ' + case)


def validate_rows(rows, label):
    if not isinstance(rows, list):
        raise ValueError(label + ' responses must be an array')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('Invalid response fields in ' + label)
        case = row['id']
        if (not isinstance(case, str) or not case or case in seen or row['verdict'] not in VERDICTS
                or not isinstance(row['reason'], str) or not row['reason'].strip()
                or not isinstance(row['source_ids'], list)
                or any(not isinstance(source, str) for source in row['source_ids'])
                or type(row['upstream_verified']) is not bool):
            raise ValueError('Duplicate, unknown or invalid response in ' + label + ': ' + str(case))
        seen.add(case)
    return rows


def anonymize(baseline, catalog):
    # Blind graders receive only items, never the mapping. Citations can make
    # condition guessable; this is concealment of labels, not a double blind.
    items, mapping = [], {}
    for kind, rows in [('baseline', validate_rows(baseline, 'baseline')),
                       ('catalog', validate_rows(catalog, 'catalog'))]:
        for row in rows:
            token = secrets.token_hex(12)
            mapping[token] = kind
            items.append(dict(token=token, **row))
    secrets.SystemRandom().shuffle(items)
    return items, mapping


def grade(items, mapping, labels, key):
    if set(labels) != set(mapping) or {row['token'] for row in items} != set(mapping) or len(items) != len(mapping):
        raise ValueError('Grades, private mapping and blind items must match')
    fields = {'evidence_accurate', 'citation_accurate', 'unsupported_claim'}
    groups, paired = {}, set()
    for row in items:
        token = row['token']
        case = row.get('id')
        if token not in mapping or mapping[token] not in {'baseline', 'catalog'}:
            raise ValueError('Unknown condition in private mapping')
        if case not in key:
            raise ValueError('Unknown blind case: ' + str(case))
        if (mapping[token], case) in paired:
            raise ValueError('Duplicate case in a condition: ' + str(case))
        paired.add((mapping[token], case))
        label = labels[token]
        if set(label) != fields or any(v is not None and type(v) is not bool for v in label.values()):
            raise ValueError('Grades require per-field true/false/null')
        for dimension in ('all', key[case]['dimension']):
            group = groups.setdefault(mapping[token], {}).setdefault(dimension, {f: [] for f in fields})
            for field in fields:
                if label[field] is not None:
                    group[field].append(label[field])
    return {kind: {dim: {f: dict(passed=sum(v), assessed=len(v), rate=sum(v)/len(v) if v else None)
                         for f, v in vals.items()} for dim, vals in dims.items()} for kind, dims in groups.items()}


def score(rows, key, data, condition):
    validate_rows(rows, condition)
    seen, failures, invalid, unchecked, misses = set(), set(), [], [], Counter()
    citation_unchecked, baseline_citations, checked_citations = [], 0, 0
    false_positives, unsupported_verified, correct, cited = 0, 0, 0, 0
    dimensions, issues = {}, {}
    for row in rows:
        case, verdict, citations = row['id'], row['verdict'], row['source_ids']
        if case not in key or case in seen:
            raise ValueError('Duplicate or unknown response: ' + str(case))
        seen.add(case)
        expected = key[case]
        kind = (('tp' if verdict == 'FAIL' else 'fn') if expected['verdict'] == 'FAIL'
                else ('fp' if verdict == 'FAIL' else 'tn'))
        dimensions.setdefault(expected.get('dimension', 'unclassified'), Counter())[kind] += 1
        issues.setdefault(expected['issue'], Counter())[kind] += 1
        cited += len(set(citations))
        if verdict == expected['verdict']:
            correct += 1
        if verdict == 'FAIL':
            if expected['verdict'] == 'FAIL':
                failures.add(case)
            else:
                false_positives += 1
        elif expected['verdict'] == 'FAIL':
            misses[expected['issue']] += 1
        if verdict == 'NOT_CHECKED':
            unchecked.append(case)
        if expected['algorithm'] is None:
            citation_unchecked.extend({'case': case, 'source': source} for source in sorted(set(citations)))
        else:
            checked_citations += len(set(citations))
            if condition == 'baseline':
                baseline_citations += len(set(citations))
            else:
                allowed = set(data['algorithms'].get(expected['algorithm'], {}).get('sources', []))
                invalid.extend({'case': case, 'source': source} for source in sorted(set(citations)) if source not in allowed)
        # This fixture ships no attested/signed upstream technical verdicts.
        if row['upstream_verified']:
            unsupported_verified += 1
    if seen != key.keys():
        raise ValueError('Missing cases: ' + ', '.join(sorted(key.keys() - seen)))
    positives = sum(r['verdict'] == 'FAIL' for r in key.values())
    negatives = len(key) - positives
    def ratio(a, b):
        return a / b if b else None

    def metrics(counts):
        tp, fp, fn, tn = (counts[k] for k in ('tp', 'fp', 'fn', 'tn'))
        precision = ratio(tp, tp + fp)
        recall = ratio(tp, tp + fn)
        specificity = ratio(tn, tn + fp)
        return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=precision, recall=recall,
                    f1=ratio(2*tp, 2*tp+fp+fn), false_positive_rate=ratio(fp, fp+tn),
                    false_negative_rate=ratio(fn, fn+tp), specificity=specificity,
                    balanced_accuracy=(recall + specificity) / 2 if recall is not None and specificity is not None else None)

    need_abstention = {case for case, expected in key.items() if expected['verdict'] == 'NOT_CHECKED'}
    return dict(total=len(key), verdicts_correct=correct, verdict_accuracy=ratio(correct, len(key)),
                true_positives=len(failures), positives=positives,
                detection_rate=ratio(len(failures), positives), false_positives=false_positives, negatives=negatives,
                false_positive_rate=ratio(false_positives, negatives), missed_issues=dict(sorted(misses.items())),
                unchecked=sorted(unchecked),
                citation_checked=checked_citations,
                citation_id_match_rate=(None if condition == 'baseline'
                                        else ratio(checked_citations - len(invalid), checked_citations)),
                baseline_citations=baseline_citations,
                citation_unchecked=citation_unchecked,
                citations_for_manual_review=sorted(invalid + citation_unchecked,
                                                   key=lambda item: (item['case'], item['source'])),
                by_fixture_issue={issue: metrics(counts) for issue, counts in sorted(issues.items())},
                by_dimension={dim: metrics(counts) for dim, counts in sorted(dimensions.items())},
                correct_abstention_rate=ratio(len(need_abstention.intersection(unchecked)), len(need_abstention)),
                defect_metrics=metrics(Counter(tp=len(failures), fp=false_positives,
                                               fn=positives-len(failures), tn=negatives-false_positives)),
                unsupported_upstream_verification_claim_rate=ratio(unsupported_verified, len(key)),
                unsupported_upstream_verification_claims=unsupported_verified,
                manual_review='Read reasons for semantic correctness; a matching source ID or verdict is not evidence that the reasoning is sound.')


def main():
    utf8_stdio()
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_subparsers(dest='action', required=True)
    a = actions.add_parser('pack')
    a.add_argument('condition', choices=('baseline', 'catalog'))
    a.add_argument('--seed', type=int, help='same case order for the same seed in both conditions')
    a = actions.add_parser('prepare')
    a.add_argument('condition', choices=('baseline', 'catalog'))
    a.add_argument('destination', type=Path)
    a.add_argument('--seed', type=int)
    a.add_argument('--repo', type=Path, help='OIBlogScore checkout to sanitize')
    a = actions.add_parser('compare')
    a.add_argument('--baseline', type=Path, required=True)
    a.add_argument('--catalog', type=Path, required=True)
    a = actions.add_parser('anonymize')
    for name in ('baseline', 'catalog', 'private-map'):
        a.add_argument('--' + name, type=Path, required=True)
    for action in ('grade', 'grade-targets'):
        a = actions.add_parser(action)
        for name in ('items', 'private-map', 'labels'):
            a.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    try:
        if args.action == 'pack':
            result = pack(args.condition, args.seed)
        elif args.action == 'prepare':
            result = prepare(args.condition, args.destination, args.seed, args.repo)
        else:
            key, data = read(FIXTURE/'key.json'), build()
            validate_key(key, read(FIXTURE/'cases.json'), data)
            if args.action == 'grade-targets':
                result = aggregate(read(args.items), read(args.private_map), read(args.labels), read(FIXTURE/'targets.json'))
            elif args.action == 'grade':
                result = grade(read(args.items), read(args.private_map), read(args.labels), key)
            else:
                rows = {kind: read(getattr(args, kind)) for kind in ('baseline', 'catalog')}
                result = {kind: score(rows[kind], key, data, kind) for kind in rows}
                if args.action == 'anonymize':
                    result, mapping = anonymize(**rows)
                    with args.private_map.open('x', encoding='utf-8') as stream:
                        json.dump(mapping, stream, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
