"""Catalog integrity regressions; these do not measure Agent performance."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'resources/algorithm-catalog'
sys.path.insert(0, str(ROOT / 'tools'))
from catalog import local_text, search
from catalog_data import build, read
from catalog_quality import check_sources
from catalog_schema import check_claims
from sync_catalog import changes, broken_references


class CatalogIntegrity(unittest.TestCase):
    def test_independent_errors_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'catalog'
            shutil.copytree(DATA, root)
            for relative in ('sources/kactl.json', 'knowledge/crosswalk.json'):
                path = root / relative
                rows = read(path)
                path.write_text(json.dumps(rows + rows[:1]), encoding='utf-8')
            self.assertGreaterEqual(sum('duplicate ID' in issue for issue in check_sources(root)), 2)
            with self.assertRaises(ValueError):
                build(root)

    def test_paths_and_custom_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path in ('../x', '/x', 'C:/x', 'C:x', '\\\\host\\share', 'a//b', 'aux.md', 'x. ', 'file:stream'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    local_text(path, root)
            with self.assertRaises(FileNotFoundError):
                local_text('missing.md', root)
            (root / 'bad.md').write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                local_text('bad.md', root)
            try:
                (root / 'link.md').symlink_to(root / 'bad.md')
            except OSError:
                pass  # Windows may disallow creating links for this account.
            else:
                with self.assertRaises(ValueError):
                    local_text('link.md', root)
            result = subprocess.run([sys.executable, str(ROOT / 'tools/catalog.py'), '--root', str(DATA),
                                     'find', 'ＳＡＭ', '--json'], cwd=root, capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)[0]['id'], 'suffix-automaton')

    def test_ranked_and_ambiguous(self):
        def card(key, title, aliases=()):
            return dict(id=key, title=title, aliases=aliases, sources=[], category='test')
        data = dict(sources={}, algorithms={r['id']: r for r in (
            card('sam', '后缀自动机'), card('variant', '广义后缀自动机', ['ＳＡＭ']),
            card('other', 'SAM'), card('extra', 'SAM variant'))})
        hits = search(data, 'ＳＡＭ')
        self.assertEqual([r['id'] for r in hits], ['sam', 'variant', 'other', 'extra'])
        self.assertTrue(hits[0]['ambiguous_exact'])
        self.assertEqual(len(search(data, 'sam', exact=True)), 3)
        self.assertEqual(len(search(data, '  ')), 4)
        self.assertEqual(search(data, '不存在'), [])

    def test_claim_verification_and_sync_refs(self):
        claim = dict(claim_id='claim', status='independently-verified', statement='Statement',
                     assumptions=[], evidence=[dict(source='invented', location='section')])
        errors = check_claims([claim, claim], {'actual'})
        for term in ('untraceable', 'derivation', 'reviewer', 'duplicate'):
            self.assertTrue(any(term in e for e in errors), errors)
        old = dict(id='a', sha256='same')
        self.assertEqual(changes([old], [dict(old, id='b')])['possible_renames'], [{'old': 'a', 'new': 'b'}])
        sid = read(DATA / 'knowledge/triage-baseline.json')['source_ids'][0]
        self.assertEqual(broken_references(DATA / 'knowledge', [sid])['triage_baseline'], [sid])
