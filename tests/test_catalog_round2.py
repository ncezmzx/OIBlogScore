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
from blind_eval import FIXTURE, pack, score


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
        self.assertEqual(len(pack('catalog')['cases']), 10)
        self.assertTrue(all(set(r)=={'id','text'} for r in pack('catalog')['cases']))
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
