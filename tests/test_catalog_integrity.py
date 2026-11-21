"""Catalog integrity regressions; these do not measure Agent performance."""
import hashlib
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

    def test_verbatim_pin_and_third_party_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'catalog'
            shutil.copytree(DATA, root)
            pin = root / 'sources/verbatim-pin.json'
            rows = json.loads(pin.read_text(encoding='utf-8'))
            rows['cp-algorithms']['revision'] = '0' * 40
            pin.write_text(json.dumps(rows), encoding='utf-8')
            self.assertTrue(any('not bound' in issue for issue in check_sources(root)))
            shutil.copy2(DATA / 'sources/verbatim-pin.json', pin)
            asset = root / 'sources/upstream/cp-algorithms/graph/dijkstra.md.txt'
            changed = asset.read_bytes() + b'\nThis proof was taken from the paper.\n'
            asset.write_bytes(changed)
            new_hash = hashlib.sha256(changed).hexdigest()
            source_file = root / 'sources/cp-algorithms.json'
            source_rows = json.loads(source_file.read_text(encoding='utf-8'))
            next(row for row in source_rows if row['id'] == 'cp-algorithms:graph/dijkstra.md')['sha256'] = new_hash
            source_file.write_text(json.dumps(source_rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            approval_file = root / 'sources/approved-verbatim.json'
            approvals = json.loads(approval_file.read_text(encoding='utf-8'))
            approvals['graph/dijkstra.md'] = new_hash
            approval_file.write_text(json.dumps(approvals, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            issues = check_sources(root)
            self.assertTrue(any('third-party provenance' in issue for issue in issues))

    def test_quality_rejects_legacy_path_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'catalog'
            shutil.copytree(DATA, root)
            index = root / 'index.json'
            rows = json.loads(index.read_text(encoding='utf-8'))
            next(row for row in rows['topics'] if row['id'] == 'cdq')['path'] = 'graph/cdq.md'
            index.write_text(json.dumps(rows), encoding='utf-8')
            self.assertTrue(any('legacy topic path' in issue for issue in check_sources(root)))

    def test_link_checker_classifies_redirects(self):
        from check_source_links import Redirected, Redirects
        handler = Redirects({'example.test'})
        with self.assertRaises(Redirected):
            handler.redirect_request(None, None, 302, 'Found', {}, 'https://publisher.test/x')

    def test_search_excludes_unmerged_candidates_by_default(self):
        data = build()
        self.assertEqual(search(data, 'dijkstra', exact=True), [])
        hits = search(data, 'dijkstra')
        self.assertEqual(hits[0]['id'], 'shortest-paths')
        self.assertEqual(hits[0]['match']['field'], 'source_title')
        candidate = next(row for row in data['algorithms'].values() if row.get('identity'))
        self.assertFalse(any(row['id'] == candidate['id'] for row in search(data, candidate['title'])))
        self.assertTrue(any(row['id'] == candidate['id']
                            for row in search(data, candidate['title'], include_candidates=True)))

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

    def test_sync_rejects_output_inside_checkout(self):
        output = ROOT / 'tmp-sync-output-for-test'
        result = subprocess.run([sys.executable, str(ROOT/'tools/sync_catalog.py'), 'cp-algorithms', str(ROOT),
                                 '--output', str(output)], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertIn('outside the OIBlogScore checkout', result.stderr)
        self.assertFalse(output.exists())

    def test_sync_cannot_repin_license_via_candidate_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            providers = read(DATA / 'sources/providers.json')
            providers['cp-algorithms']['policy_sha256'] = '0' * 64
            profiles = root / 'candidate.json'
            profiles.write_text(json.dumps(providers), encoding='utf-8')
            output = root / 'staged'
            result = subprocess.run([sys.executable, str(ROOT/'tools/sync_catalog.py'), 'cp-algorithms', str(root),
                                     '--providers', str(profiles), '--output', str(output)], capture_output=True, encoding='utf-8')
            self.assertEqual(result.returncode, 2)
            self.assertIn('licensing policy', result.stderr)
            self.assertFalse(output.exists())

    def test_large_text_and_license_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / 'large.md'
            with payload.open('wb') as stream:
                stream.truncate(8 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, 'text exceeds'):
                local_text('large.md', root)
            data = root / 'data'
            shutil.copytree(DATA, data)
            license_file = data/'sources/upstream/cp-algorithms/LICENSE.txt'
            original = root/'original.txt'
            license_file.replace(original)
            try:
                license_file.symlink_to(original)
            except OSError:
                return  # No link-create permission on some Windows runners.
            self.assertTrue(any('is a link' in issue for issue in check_sources(data)))

    def test_fixed_cohort_membership(self):
        from hashlib import sha256
        cohort = read(DATA/'knowledge/triage-baseline.json')
        self.assertEqual(cohort['revision'], '705047c09cc1ea3e50b487ea865f9403f9908fad')
        self.assertEqual(sha256('\n'.join(cohort['source_ids']).encode()).hexdigest(),
                         'd6c1c78f296dcaefa66bebc46b04994ae62d1a053e4d730865bfd599f7d03919')

    def test_editorial_expansion_is_opt_in_and_never_exact(self):
        data = build()
        default = search(data, 'link-cut-tree')
        expanded = search(data, 'link-cut-tree', include_related=True)
        self.assertEqual(expanded[:len(default)], default)
        weak = [r for r in expanded if r['match']['field'] == 'editorial_relation']
        self.assertTrue(weak)
        self.assertTrue(all(r['match']['value'] == 'link-cut-tree' for r in weak))
        self.assertEqual([r['id'] for r in search(data, 'link-cut-tree', exact=True, include_related=True)], ['link-cut-tree'])

    def test_candidate_approval_binds_exact_pin_and_policy(self):
        from sync_catalog import candidate_approval
        config = {'revision': 'a'*40, 'policy_sha256': 'b'*64}
        files = {'fixture.md': 'c'*64}
        self.assertEqual(candidate_approval(dict(config, files=files), config), files)
        for approval in (files, dict(config, files=files, revision='d'*40), dict(config, files=files, policy_sha256='0'*64)):
            with self.assertRaisesRegex(ValueError, 'Approval must name'):
                candidate_approval(approval, config)

    def test_search_explains_claims_and_rejects_oversized_query(self):
        data = build()
        row = search(data, 'segment-tree-beats', exact=True)[0]
        self.assertTrue(row['has_review'])
        self.assertEqual(row['claim_states'], ['project-analysis'])
        with self.assertRaisesRegex(ValueError, '4096'):
            search(data, 'x'*4097)
