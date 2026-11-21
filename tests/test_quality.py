"""Run the authoring gate and its executable tools through production entry points."""
from itertools import product
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def run(relative, *args):
    return subprocess.run([sys.executable, str(ROOT / relative), *map(str, args)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')


class Quality(unittest.TestCase):
    def test_offline_quality_gate(self):
        p = run('tools/check_quality.py')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_quality_gate_rejects_unindexed_topic_and_broken_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('skills', 'resources'):
                shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            book = root / 'resources' / 'algorithm-catalog'
            (book / 'graph/orphan.md').write_text('# Heading only\n', encoding='utf-8')
            skill = root / 'skills' / 'oi-proof-review' / 'SKILL.md'
            skill.write_text(skill.read_text(encoding='utf-8') + '\n[bad](references/absent.md)\n', encoding='utf-8')
            p = run('tools/check_quality.py', '--root', root)
            self.assertEqual(p.returncode, 1)
            for diagnostic in ('empty knowledge text', 'dangling link', 'Catalog index/file mismatch'):
                self.assertIn(diagnostic, p.stderr)

    def test_catalog_alias_and_single_reference_lookup(self):
        p = run('tools/catalog.py', 'find', 'ＣＤＱ', '--exact', '--category', 'divide-and-conquer', '--json')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual([item['id'] for item in json.loads(p.stdout)], ['cdq'])
        body = run('tools/catalog.py', 'show', 'cdq')
        self.assertEqual(body.returncode, 0, body.stderr)
        self.assertIn('## 成立条件', body.stdout)
        self.assertEqual(run('tools/catalog.py', 'show', 'absent').returncode, 2)
        self.assertEqual(run('tools/catalog.py', 'find', 'absent').returncode, 1)

    def test_proof_ledger_positive_blocked_and_invalid(self):
        def row(id_, direction, status='PASS', needs=()):
            return dict(id=id_, direction=direction, status=status, depends_on=list(needs),
                        location='note.md:4', evidence='Documented directional argument')

        script = 'skills/oi-proof-review/scripts/check_ledger.py'
        fwd = row('f', 'forward')
        rev = row('r', 'reverse')
        goal = row('g', 'equivalence', needs=('f', 'r'))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'proof.json'
            for rows, code, detail in [
                ([fwd, rev, goal], 0, 'structurally complete'),
                ([fwd, dict(rev, status='FAIL'), dict(goal, status='FAIL')], 1, 'Blocked targets'),
                ([fwd, dict(goal, depends_on=['f'])], 2, 'both directions'),
                ([fwd, dict(rev, depends_on=['missing']), goal], 2, 'Unknown claim'),
                ([dict(fwd, depends_on=['r']), dict(rev, depends_on=['f']), goal], 2, 'Cyclic dependencies'),
                ([dict(fwd, status='SUSPECTED'), rev, goal], 2, 'unresolved or failed')]:
                with self.subTest(detail=detail):
                    path.write_text(json.dumps(dict(targets=['g'], claims=rows)), encoding='utf-8')
                    p = run(script, path)
                    self.assertEqual(p.returncode, code, p.stderr)
                    self.assertIn(detail, p.stdout + p.stderr)

    def test_selected_reference_witnesses_against_small_oracles(self):
        # Verify the literal CRT, collision, and 2-SAT witnesses used in the catalog.
        self.assertFalse(any(x % 4 == 0 and x % 6 == 1 for x in range(12)))
        self.assertEqual([(2 * a + b) % 5 for a, b in [(1, 3), (2, 1)]], [0, 0])
        self.assertEqual([x for x in (False, True) if x or x], [True])
        self.assertTrue(any((x or y or z) and not ((x or y) and (x or z) and (y or z))
                            for x, y, z in product((False, True), repeat=3)))
