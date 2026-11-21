#!/usr/bin/env python3
"""Export blinded case prompts and compare two independently collected Agent runs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import secrets

from catalog_data import ROOT, build, read
from target_grading import aggregate

FIXTURE = ROOT.parents[1] / 'tests/fixtures/blind'
VERDICTS = {'PASS','FAIL','NOT_CHECKED'}


def pack(condition, seed=None):
    access = ('Use the catalog when relevant; cite source IDs and state whether you independently verified the claim.'
              if condition == 'catalog' else 'Do not access the Catalog, references, or external tools. Use reasoning from the excerpt.')
    cases = read(FIXTURE / 'cases.json')
    if seed is not None:
        import random
        random.Random(seed).shuffle(cases)
    return {'condition': condition, 'seed': seed, 'instruction': access + ' Return one row per case with id, verdict (PASS, FAIL or NOT_CHECKED), reason, source_ids, and upstream_verified (true only if claiming upstream content itself is verified).',
            'cases': cases}


def validate_key(key, cases, data):
    ids = [row['id'] for row in cases]
    if len(ids) != len(set(ids)) or set(ids) != key.keys():
        raise ValueError('Blind cases and keys must correspond one-to-one')
    for case, row in key.items():
        if (row['verdict'] not in VERDICTS or row['dimension'] not in {'algorithm','proof','complexity','code'}
                or not row['basis'].strip() or (row['algorithm'] is not None and row['algorithm'] not in data['algorithms'])):
            raise ValueError('Invalid private answer key: ' + case)


def anonymize(baseline, catalog):
    # Blind graders receive only items, never the mapping. Citations can make
    # condition guessable; this is concealment of labels, not a double blind.
    items, mapping = [], {}
    for kind, rows in [('baseline', baseline), ('catalog', catalog)]:
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
    groups = {}
    for row in items:
        token = row['token']
        label = labels[token]
        if set(label) != fields or any(v is not None and type(v) is not bool for v in label.values()):
            raise ValueError('Grades require per-field true/false/null')
        for dimension in ('all', key[row['id']]['dimension']):
            group = groups.setdefault(mapping[token], {}).setdefault(dimension, {f: [] for f in fields})
            for field in fields:
                if label[field] is not None:
                    group[field].append(label[field])
    return {kind: {dim: {f: dict(passed=sum(v), assessed=len(v), rate=sum(v)/len(v) if v else None)
                         for f, v in vals.items()} for dim, vals in dims.items()} for kind, dims in groups.items()}


def score(rows, key, data, condition):
    if not isinstance(rows, list):
        raise ValueError('Responses must be an array')
    seen, failures, invalid, unchecked, misses = set(), set(), [], [], Counter()
    false_positives, unsupported_verified, correct, cited = 0, 0, 0, 0
    dimensions, issues = {}, {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id','verdict','reason','source_ids','upstream_verified'}:
            raise ValueError('Invalid response fields')
        case, verdict, citations = row['id'], row['verdict'], row['source_ids']
        if (case not in key or case in seen or verdict not in VERDICTS or not isinstance(row['reason'], str) or not row['reason'].strip()
                or not isinstance(citations, list) or any(not isinstance(s, str) for s in citations) or type(row['upstream_verified']) is not bool):
            raise ValueError('Duplicate, unknown or invalid response: ' + str(case))
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
        allowed = set(data['algorithms'].get(expected['algorithm'], {}).get('sources', []))
        invalid.extend({'case':case,'source':sid} for sid in set(citations) if sid not in allowed or condition == 'baseline')
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
        return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=ratio(tp, tp+fp), recall=ratio(tp, tp+fn),
                    f1=ratio(2*tp, 2*tp+fp+fn), false_positive_rate=ratio(fp, fp+tn), false_negative_rate=ratio(fn, fn+tp))

    need_abstention = {case for case, expected in key.items() if expected['verdict'] == 'NOT_CHECKED'}
    return dict(total=len(key), verdicts_correct=correct, true_positives=len(failures), positives=positives,
                detection_rate=ratio(len(failures), positives), false_positives=false_positives, negatives=negatives,
                false_positive_rate=ratio(false_positives, negatives), missed_issues=dict(misses), unchecked=sorted(unchecked),
                citations_for_manual_review=sorted(invalid, key=lambda item: (item['case'],item['source'])),
                by_fixture_issue={issue: metrics(counts) for issue, counts in sorted(issues.items())},
                by_dimension={dim: metrics(counts) for dim, counts in sorted(dimensions.items())},
                correct_abstention_rate=ratio(len(need_abstention.intersection(unchecked)), len(need_abstention)),
                defect_metrics=metrics(Counter(tp=len(failures), fp=false_positives,
                                               fn=positives-len(failures), tn=negatives-false_positives)),
                citation_id_match_rate=ratio(cited-len(invalid), cited),
                unsupported_upstream_verification_claim_rate=ratio(unsupported_verified, len(key)),
                unsupported_upstream_verification_claims=unsupported_verified,
                manual_review='Read reasons for semantic correctness; a matching source ID or verdict is not evidence that the reasoning is sound.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_subparsers(dest='action', required=True)
    a = actions.add_parser('pack')
    a.add_argument('condition', choices=('baseline','catalog'))
    a.add_argument('--seed', type=int, help='same case order for the same seed in both conditions')
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
        else:
            key, data = read(FIXTURE/'key.json'), build()
            validate_key(key, read(FIXTURE/'cases.json'), data)
            if args.action == 'grade-targets':
                result = aggregate(read(args.items), read(args.private_map), read(args.labels), read(FIXTURE/'targets.json'))
            elif args.action == 'grade':
                result = grade(read(args.items), read(args.private_map), read(args.labels), key)
            else:
                rows = {kind: read(getattr(args, kind)) for kind in ('baseline','catalog')}
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
