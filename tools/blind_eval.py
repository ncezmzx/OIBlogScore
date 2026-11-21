#!/usr/bin/env python3
"""Export blinded case prompts and compare two independently collected Agent runs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from catalog_data import ROOT, build, read

FIXTURE = ROOT.parents[1] / 'tests/fixtures/blind'
VERDICTS = {'PASS','FAIL','NOT_CHECKED'}


def pack(condition):
    access = ('Use the catalog when relevant; cite source IDs and state whether you independently verified the claim.'
              if condition == 'catalog' else 'Do not access the Catalog, references, or external tools. Use reasoning from the excerpt.')
    return {'condition': condition, 'instruction': access + ' Return one row per case with id, verdict (PASS, FAIL or NOT_CHECKED), reason, source_ids, and upstream_verified (true only if claiming upstream content itself is verified).',
            'cases': read(FIXTURE / 'cases.json')}


def score(rows, key, data, condition):
    if not isinstance(rows, list):
        raise ValueError('Responses must be an array')
    seen, failures, invalid, unchecked, misses = set(), set(), [], [], Counter()
    false_positives, unsupported_verified, correct, cited = 0, 0, 0, 0
    dimensions = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id','verdict','reason','source_ids','upstream_verified'}:
            raise ValueError('Invalid response fields')
        case, verdict, citations = row['id'], row['verdict'], row['source_ids']
        if (case not in key or case in seen or verdict not in VERDICTS or not isinstance(row['reason'], str) or not row['reason'].strip()
                or not isinstance(citations, list) or any(not isinstance(s, str) for s in citations) or type(row['upstream_verified']) is not bool):
            raise ValueError('Duplicate, unknown or invalid response: ' + str(case))
        seen.add(case)
        expected = key[case]
        counts = dimensions.setdefault(expected['issue'], Counter())
        counts[('tp' if verdict == 'FAIL' else 'fn') if expected['verdict'] == 'FAIL'
               else ('fp' if verdict == 'FAIL' else 'tn')] += 1
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
                    false_positive_rate=ratio(fp, fp+tn), false_negative_rate=ratio(fn, fn+tp))

    return dict(total=len(key), verdicts_correct=correct, true_positives=len(failures), positives=positives,
                detection_rate=ratio(len(failures), positives), false_positives=false_positives, negatives=negatives,
                false_positive_rate=ratio(false_positives, negatives), missed_issues=dict(misses), unchecked=sorted(unchecked),
                citations_for_manual_review=sorted(invalid, key=lambda item: (item['case'],item['source'])),
                by_fixture_issue={issue: metrics(counts) for issue, counts in sorted(dimensions.items())},
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
    a = actions.add_parser('compare')
    a.add_argument('--baseline', type=Path, required=True)
    a.add_argument('--catalog', type=Path, required=True)
    args = p.parse_args()
    try:
        if args.action == 'pack':
            result = pack(args.condition)
        else:
            key, data = read(FIXTURE/'key.json'), build()
            result = {kind: score(read(getattr(args, kind)), key, data, kind) for kind in ('baseline','catalog')}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
