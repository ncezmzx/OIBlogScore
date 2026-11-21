"""Aggregate independently adjudicated targets, not an automated proof judge."""
from collections import Counter

DISPOSITIONS = {'FAIL', 'PASS', 'NOT_CHECKED', 'CONDITIONAL'}
FLAGS = ('evidence_accurate', 'citation_accurate', 'unsupported_claim')


def aggregate(items, mapping, labels, rubric):
    selected = [item for item in items if item['id'] in rubric]
    tokens = {item['token'] for item in selected}
    if len(tokens) != len(selected) or tokens != labels.keys() or not tokens <= mapping.keys():
        raise ValueError('Labels must cover each selected blind response once')
    output, paired = {}, set()
    for item in selected:
        case, token = item['id'], item['token']
        condition = mapping[token]
        if condition not in {'baseline', 'catalog'} or (condition, case) in paired:
            raise ValueError('Invalid or duplicate case condition')
        paired.add((condition, case))
        targets = rubric[case]
        decisions = labels[token]
        if decisions.keys() != targets.keys():
            raise ValueError('Each target needs an explicit adjudication or null')
        result = output.setdefault(condition, {'cases': {}, 'totals': Counter()})
        result['cases'][case] = detail = {}
        excerpts = set()
        for tid, expected in targets.items():
            target = decisions[tid]
            correct = None
            if target is not None:
                if (set(target) != {'excerpt', 'disposition', *FLAGS} or target['disposition'] not in DISPOSITIONS
                        or not isinstance(target['excerpt'], str) or not target['excerpt'].strip()
                        or target['excerpt'] not in item['reason'] or target['excerpt'] in excerpts
                        or any(target[f] is not None and type(target[f]) is not bool for f in FLAGS)):
                    raise ValueError('Adjudication needs a distinct verbatim excerpt and valid labels')
                excerpts.add(target['excerpt'])
                correct = target['disposition'] == expected['disposition']
            detail[tid] = {'expected': expected['disposition'], 'judgment': target, 'correct': correct}
            count = result['totals']
            count['targets'] += 1
            count['correct'] += int(correct is True)
            if correct is not None:
                count['assessed'] += 1
                count['assessed_correct'] += int(correct)
            if expected['disposition'] == 'NOT_CHECKED':
                count['abstention_opportunities'] += 1
                count['correct_abstentions'] += int(correct is True)
            if expected['disposition'] == 'PASS':
                count['negative_targets'] += 1
                count['false_alarms'] += int(target is not None and target['disposition'] in ('FAIL', 'CONDITIONAL'))
            if expected['disposition'] in ('FAIL', 'CONDITIONAL'):
                count['defects'] += 1
                count['detected'] += int(correct is True)
            if target is not None and target['disposition'] in ('FAIL', 'CONDITIONAL'):
                count['defect_assertions'] += 1
            for field in FLAGS:
                if target is not None and target[field] is not None:
                    count[field + '_n'] += 1
                    count[field] += int(target[field])
    if paired != {(c, case) for c in ('baseline', 'catalog') for case in rubric}:
        raise ValueError('Both conditions must cover the full target rubric')
    def rate(a, b):
        return a / b if b else None
    for result in output.values():
        c = result['totals']
        result['rates'] = dict(target_accuracy=rate(c['correct'], c['targets']),
                               assessed_accuracy=rate(c['assessed_correct'], c['assessed']),
                               scoped_precision=rate(c['detected'], c['defect_assertions']),
                               scoped_recall=rate(c['detected'], c['defects']),
                               scoped_f1=rate(2*c['detected'], c['defects'] + c['defect_assertions']),
                               scoped_false_negative_rate=rate(c['defects']-c['detected'], c['defects']),
                               scoped_false_positive_rate=rate(c['false_alarms'], c['negative_targets']),
                               correct_abstention=rate(c['correct_abstentions'], c['abstention_opportunities']),
                               **{f: rate(c[f], c[f + '_n']) for f in FLAGS})
    return output
