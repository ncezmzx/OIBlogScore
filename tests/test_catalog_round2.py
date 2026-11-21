import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'resources/algorithm-catalog'
sys.path.insert(0, str(ROOT/'tools'))
from catalog_quality import check_sources
from catalog_data import build, read
from blind_eval import FIXTURE, pack, prepare, score


def cli(script, *args):
    return subprocess.run([sys.executable, str(ROOT/'tools'/script), *map(str,args)], capture_output=True, encoding='utf-8')


class CatalogRound2(unittest.TestCase):
    def test_typed_retrieval_and_cohort(self):
        variants = json.loads(cli('catalog.py', 'variants', 'shortest-paths', '--json').stdout)
        self.assertTrue(any(r['id']=='cp-algorithms:graph/dijkstra_sparse.md' and r['relation']=='variant' for r in variants))
        matches = json.loads(cli('catalog.py','search-sources','Slope Trick','--author','zscoder','--kind','blog','--json').stdout)
        self.assertEqual([r['id'] for r in matches], ['codeforces:47821'])
        self.assertEqual(matches[0]['license_terms']['commercial_use'], 'unknown')
        data = json.loads(cli('catalog.py','stats').stdout)
        triage = data['triage']
        self.assertEqual(triage['mapped'] + triage['pending'], triage['total'])
        pending = json.loads(cli('catalog.py','candidates').stdout)
        self.assertEqual(len(pending), triage['pending'])
        self.assertTrue(all(not row['mapped'] for row in pending))

    def test_schema_rejects_license_and_wrong_url(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)/'data'
            shutil.copytree(DATA,dest)
            p = dest/'sources/providers.json'
            providers = read(p)
            providers['cp-algorithms']['terms']['share_alike'] = 'not-required'
            p.write_text(json.dumps(providers))
            p = dest/'sources/cp-algorithms.json'
            rows = read(p)
            rows[0]['url'] = 'https://cp-algorithms.com/incorrect.html'
            p.write_text(json.dumps(rows))
            errors = check_sources(dest)
            self.assertTrue(any('ShareAlike' in e for e in errors))
            self.assertTrue(any('do not correspond' in e for e in errors))

    def test_crosswalk_rejects_conflicting_identity_and_dangling_source(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)/'data'
            shutil.copytree(DATA,dest)
            p = dest/'knowledge/crosswalk.json'
            rows = read(p)
            rows[0]['sources'].append(dict(source='oi-wiki:ds/sparse-table.md',relation='exact',basis='invalid fixture'))
            rows[1]['sources'].append(dict(source='does-not-exist',relation='variant',basis='invalid fixture'))
            p.write_text(json.dumps(rows))
            errors = check_sources(dest)
            self.assertTrue(any('conflicting identity claims' in e for e in errors))
            self.assertTrue(any('unresolved evidence' in e for e in errors))

    def test_review_schema_rejects_fake_verification_and_template(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)/'data'; shutil.copytree(DATA,dest)
            p = dest/'knowledge/review.json'; notes = read(p)
            notes['polynomial']['status'] = 'VERIFIED'
            notes['digit-dp']['proof'] = 'TODO'
            p.write_text(json.dumps(notes))
            errors = check_sources(dest)
            self.assertIn('polynomial: incomplete or untraceable project reasoning', errors)
            self.assertIn('digit-dp: empty/template proof', errors)

    def test_duplicate_json_key_is_rejected_before_composition(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'invalid.json'
            p.write_text('{"id":1,"id":2}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                read(p)

    def test_skill_contract_lints_more_than_script_name(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            for directory in ('skills','resources','tools'):
                shutil.copytree(ROOT/directory, dest/directory)
            p = dest/'skills/oi-proof-review/SKILL.md'
            p.write_text('\n'.join(line for line in p.read_text(encoding='utf-8').splitlines()
                                   if not line.startswith('- **缺证处理**：')), encoding='utf-8')
            result = cli('check_quality.py','--root',dest)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('missing Catalog contract: 缺证处理',result.stderr)

    def test_blind_packs_and_synthetic_comparison(self):
        key = read(FIXTURE/'key.json'); data = build()
        self.assertEqual(pack('catalog')['cases'], pack('baseline')['cases'])
        self.assertEqual(len(pack('catalog')['cases']), 25)
        self.assertTrue(all(set(r)=={'id','text'} for r in pack('catalog')['cases']))
        manifest = pack('baseline', 7)['manifest']
        self.assertEqual(manifest['seed'], 7)
        self.assertRegex(manifest['cases_sha256'], '^[0-9a-f]{64}$')
        self.assertRegex(manifest['catalog_sha256'], '^[0-9a-f]{64}$')
        rows = [dict(id=k,verdict=v['verdict'],reason='synthetic scoring fixture',source_ids=[],upstream_verified=False) for k,v in key.items()]
        wrong = [dict(r) for r in rows]
        wrong[0].update(verdict='FAIL',source_ids=['does-not-exist'],upstream_verified=True)
        wrong[1].update(verdict='PASS')
        with self.assertRaisesRegex(ValueError,'Missing cases'):
            score(rows[:-1],key,data,'catalog')
        with tempfile.TemporaryDirectory() as temp:
            catalog = Path(temp)/'catalog.json'; catalog.write_text(json.dumps(rows))
            baseline = Path(temp)/'baseline.json'; baseline.write_text(json.dumps(wrong))
            result = cli('blind_eval.py','compare','--baseline',baseline,'--catalog',catalog)
            self.assertEqual(result.returncode,0,result.stderr)
            scores = json.loads(result.stdout)
            self.assertEqual(scores['catalog']['detection_rate'],1)
            self.assertEqual(scores['baseline']['false_positives'],1)
            self.assertEqual(scores['baseline']['missed_issues'],{'negative-edge':1})
            self.assertEqual(scores['baseline']['unsupported_upstream_verification_claims'],1)

    def test_prepare_writes_sanitized_bundles(self):
        with tempfile.TemporaryDirectory() as temp:
            base, catalog = Path(temp)/'baseline', Path(temp)/'catalog'
            result = prepare('baseline', base, seed=7, repo=ROOT)
            self.assertEqual(result['manifest']['seed'], 7)
            self.assertTrue((base/'cases.json').is_file())
            self.assertTrue((base/'instruction.txt').is_file())
            self.assertFalse((base/'repo').exists())
            prepare('catalog', catalog, seed=7, repo=ROOT)
            self.assertTrue((catalog/'repo'/'tools'/'catalog.py').is_file())
            self.assertTrue((catalog/'repo'/'resources'/'algorithm-catalog'/'index.json').is_file())
            self.assertFalse((catalog/'repo'/'tests').exists())
            for destination in (base, catalog):
                self.assertFalse(any(destination.rglob('key.json')))
                self.assertFalse(any(destination.rglob('targets.json')))
            self.assertEqual(result['manifest']['cases_sha256'],
                             json.loads((catalog/'manifest.json').read_text(encoding='utf-8'))['cases_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp)/'exists'; existing.mkdir()
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare('baseline', existing, repo=ROOT)
        with self.assertRaisesRegex(ValueError, 'outside'):
            prepare('baseline', ROOT/'tmp-eval-bundle-for-test', repo=ROOT)

    def test_citation_metrics_separate_unverifiable_and_baseline(self):
        key = {'A01': {'verdict': 'PASS', 'issue': 'none', 'algorithm': 'shortest-paths', 'dimension': 'proof'},
               'A10': {'verdict': 'NOT_CHECKED', 'issue': 'missing-spec', 'algorithm': None, 'dimension': 'complexity'}}
        data = {'algorithms': {'shortest-paths': {'sources': []}}}
        rows = [dict(id='A01', verdict='PASS', reason='ok', source_ids=['nope'], upstream_verified=False),
                dict(id='A10', verdict='NOT_CHECKED', reason='missing', source_ids=['also-nope'], upstream_verified=False)]
        result = score(rows, key, data, 'catalog')
        self.assertEqual(result['citation_checked'], 1)
        self.assertEqual(result['citation_id_match_rate'], 0)
        self.assertEqual(len(result['citation_unchecked']), 1)
        baseline = score(rows, key, data, 'baseline')
        self.assertIsNone(baseline['citation_id_match_rate'])
        self.assertEqual(baseline['baseline_citations'], 1)
        self.assertEqual(len(baseline['citations_for_manual_review']), 1)

    def test_grade_rejects_duplicate_condition_and_unknown_condition(self):
        from blind_eval import grade
        key = read(FIXTURE/'key.json')
        items = [dict(id='A01', verdict='PASS', reason='x', source_ids=[], upstream_verified=False, token='a'),
                 dict(id='A01', verdict='PASS', reason='y', source_ids=[], upstream_verified=False, token='b')]
        mapping = {'a': 'baseline', 'b': 'baseline'}
        labels = {token: dict(evidence_accurate=True, citation_accurate=None, unsupported_claim=False) for token in mapping}
        with self.assertRaisesRegex(ValueError, 'Duplicate case'):
            grade(items, mapping, labels, key)
        mapping['b'] = 'zoo'
        with self.assertRaisesRegex(ValueError, 'condition'):
            grade(items, mapping, labels, key)

    def test_blind_anonymize_and_human_metrics(self):
        from blind_eval import anonymize, grade
        key = read(FIXTURE/'key.json')
        baseline = [dict(id='A01', verdict='PASS', reason='witness', source_ids=[], upstream_verified=False)]
        items, mapping = anonymize(baseline, baseline)
        self.assertEqual(len(set(mapping)), 2)
        self.assertTrue(all('condition' not in row for row in items))
        rows = {row['token']: dict(evidence_accurate=True, citation_accurate=None, unsupported_claim=False) for row in items}
        stats = grade(items, mapping, rows, key)
        self.assertEqual(stats['catalog']['proof']['evidence_accurate']['rate'], 1)
        self.assertIsNone(stats['baseline']['proof']['citation_accurate']['rate'])
        with self.assertRaises(ValueError):
            grade(items, mapping, {}, key)

    def test_seeded_pack_and_f1_denominators(self):
        self.assertEqual(pack('baseline', 17)['cases'], pack('catalog', 17)['cases'])
        self.assertNotEqual(pack('baseline', 17)['cases'], pack('baseline', 18)['cases'])
        key = {'x': dict(verdict='PASS', issue='none', algorithm=None, dimension='proof')}
        row = dict(id='x', verdict='PASS', reason='synthetic', source_ids=[], upstream_verified=False)
        metrics = score([row], key, {'algorithms': {}}, 'baseline')['defect_metrics']
        self.assertIsNone(metrics['precision'])
        self.assertIsNone(metrics['recall'])
        self.assertIsNone(metrics['f1'])
        row['verdict'] = 'FAIL'
        metrics = score([row], key, {'algorithms': {}}, 'baseline')['defect_metrics']
        self.assertEqual((metrics['f1'], metrics['false_positive_rate']), (0, 1))

    def test_target_grade_separates_miss_bad_evidence_and_conditional(self):
        from target_grading import aggregate
        rubric = read(FIXTURE/'targets.json')
        one = dict(id='A25', reason='knuth cost types missing')
        items = [dict(one, token='x'), dict(one, token='y')]
        mapping = {'x': 'baseline', 'y': 'catalog'}
        def label(excerpt, disposition, evidence=True, citation=None):
            return dict(excerpt=excerpt, disposition=disposition, evidence_accurate=evidence,
                        citation_accurate=citation, unsupported_claim=not evidence)
        correct = {'knuth-window': label('knuth','PASS'), 'resort': label('cost','FAIL'),
                   'product-type': label('types','CONDITIONAL'), 'unknown-preprocess': label('missing','NOT_CHECKED')}
        imperfect = dict(correct, **{'resort': None, 'product-type': label('types','FAIL',True,False),
                                     'knuth-window': label('knuth','PASS',False)})
        result = aggregate(items, mapping, {'x': imperfect, 'y': correct}, rubric)
        self.assertEqual(result['catalog']['rates']['scoped_recall'], 1)
        self.assertEqual(result['catalog']['rates']['assessed_accuracy'], 1)
        self.assertIsNone(result['catalog']['rates']['citation_accurate'])
        rows = result['baseline']['cases']['A25']
        self.assertIsNone(rows['resort']['correct'])
        self.assertFalse(rows['product-type']['correct'])
        self.assertTrue(rows['knuth-window']['correct'])
        self.assertFalse(rows['knuth-window']['judgment']['evidence_accurate'])
        self.assertEqual(result['baseline']['rates']['correct_abstention'], 1)
        self.assertEqual(result['baseline']['rates']['scoped_precision'], 0)
        self.assertAlmostEqual(result['baseline']['rates']['assessed_accuracy'], 2/3)
        with self.assertRaisesRegex(ValueError, 'distinct'):
            aggregate(items, mapping, {'x': dict(correct, resort=label('knuth','FAIL')), 'y': correct}, rubric)
