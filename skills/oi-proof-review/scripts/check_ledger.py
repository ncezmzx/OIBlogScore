#!/usr/bin/env python3
"""Validate the standalone proof ledger; no semantic verdict or external dependencies."""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import sys


class LedgerError(ValueError):
    """Invalid or contradictory proof record."""


def strings(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def inspect(record):
    if not isinstance(record, dict):
        raise LedgerError('Ledger must be an object')
    targets, rows = record.get('targets'), record.get('claims')
    if not strings(targets) or not targets or len(set(targets)) != len(targets):
        raise LedgerError('Expected distinct target IDs')
    if not isinstance(rows, list):
        raise LedgerError('Expected a claims array')
    claims, parents, outstanding = {}, defaultdict(list), {}
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('id', 'location', 'evidence')):
            raise LedgerError('Each claim requires id, location and evidence')
        key = row['id']
        deps = row.get('depends_on')
        if key in claims or not strings(deps) or len(set(deps)) != len(deps):
            raise LedgerError('Duplicate ID or invalid dependencies: ' + key)
        if row.get('direction') not in ('statement', 'forward', 'reverse', 'equivalence') or row.get('status') not in ('PASS', 'FAIL', 'SUSPECTED', 'NOT_CHECKED'):
            raise LedgerError('Unknown direction or status: ' + key)
        claims[key] = row
        outstanding[key] = len(deps)
        for dep in deps:
            parents[dep].append(key)
    unknown = (set(targets) | set(parents)) - claims.keys()
    if unknown:
        raise LedgerError('Unknown claim IDs: ' + ', '.join(sorted(unknown)))
    for key, row in claims.items():
        if row['direction'] == 'equivalence':
            directions = [claims[dep]['direction'] for dep in row['depends_on']]
            if directions.count('forward') != 1 or directions.count('reverse') != 1:
                raise LedgerError('Equivalence requires both directions: ' + key)
    ready = deque(key for key, count in outstanding.items() if count == 0)
    complete = {}
    while ready:
        key = ready.popleft()
        row = claims[key]
        complete[key] = row['status'] == 'PASS' and all(complete[dep] for dep in row['depends_on'])
        if row['status'] == 'PASS' and not complete[key]:
            raise LedgerError('PASS has unresolved or failed prerequisites: ' + key)
        for parent in parents[key]:
            outstanding[parent] -= 1
            if outstanding[parent] == 0:
                ready.append(parent)
    if len(complete) != len(claims):
        raise LedgerError('Cyclic dependencies among: ' + ', '.join(key for key in claims if key not in complete))
    return [key for key in targets if not complete[key]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    args = parser.parse_args(argv)
    try:
        blocked = inspect(json.loads(args.ledger.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print('Blocked targets: ' + ', '.join(blocked) if blocked else 'Ledger structurally complete')
    return int(bool(blocked))


if __name__ == '__main__':
    sys.exit(main())
