"""Tests for catalog evidence routing, local oracles, and upstream snapshot safety."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'resources' / 'algorithm-catalog'
FIXTURES = ROOT / 'tests' / 'fixtures' / 'catalog'
sys.path.insert(0, str(ROOT / 'tools'))
from catalog_data import build  # noqa: E402
from catalog_quality import check_sources  # noqa: E402
from sync_catalog import changes, records, sha  # noqa: E402


def command(name, *args):
    return subprocess.run([sys.executable, str(ROOT/'tools'/name), *map(str,args)],
                          capture_output=True, encoding='utf-8')


class CatalogTests(unittest.TestCase):
    def test_canonical_bilingual_aliases(self):
        for aliases, expected in [(['李超线段树', 'Li Chao Tree'],'li-chao'),
                                  (['树链剖分','ＨＬＤ'],'heavy-light'),
                                  (['强连通分量','SCC'],'scc'),
                                  (['后缀自动机','SAM'],'suffix-automaton'),
                                  (['斜率优化','Convex Hull Trick'],'convex-hull'),
                                  (['线段树优化 DP','Segment Tree Optimized DP'],'segment-tree-dp')]:
            for alias in aliases:
                run = command('catalog.py', 'find', alias, '--json')
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual([r['id'] for r in json.loads(run.stdout)], [expected])

    def test_golden_evidence_routes(self):
        for item in json.loads((FIXTURES/'golden.json').read_text(encoding='utf-8')):
            with self.subTest(item=item['id']):
                result = json.loads(command('catalog.py', 'find', item['query'], '--json').stdout)
                self.assertEqual(result[0]['id'], item['algorithm'])
                refs = json.loads(command('catalog.py', 'refs', item['algorithm'], '--json').stdout)
                row = next(row for row in refs if row['id'] == item['source'])
                self.assertEqual(row['trust'], 'upstream-unreviewed')
                if 'excerpt' in item:
                    self.assertIn(item['excerpt'], (DATA/'sources'/row['text_path']).read_text(encoding='utf-8'))
                self.assertNotEqual(item['correct'], item['incorrect'])

    def test_golden_independent_witnesses(self):
        case = json.loads((FIXTURES/'golden.json').read_text(encoding='utf-8'))[0]['witness']
        dist = [0, float('inf'), float('inf')]
        for _ in range(2):
            dist = [min([dist[v]] + [dist[u] + w for u, dest, w in case['edges'] if dest == v]) for v in range(3)]
        self.assertEqual(dist[case['vertex']], case['distance'])
        self.assertEqual([n for n in range(1, 11) if '0' in str(n)], [10])
        self.assertEqual(sum(abs(a-b) for a,b in zip([0,0],[999,999])), 1998)

    @unittest.skipUnless(shutil.which('g++'), 'g++ not installed')
    def test_cpp_golden_correct_and_broken(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp)/'a.out'
            for flags, expected in [([], '4'), (['-DBROKEN'], '6')]:
                subprocess.run(['g++', '-std=c++17', *flags, str(FIXTURES/'lazy.cpp'), '-o', str(exe)], check=True, timeout=15)
                self.assertEqual(subprocess.check_output([str(exe)], text=True, timeout=3).strip(), expected)

    def test_filtered_sources_related_and_unreviewed_boundary(self):
        p = command('catalog.py', 'search-sources', 'potentials', '--kind', 'blog', '--provider', 'codeforces', '--tag', 'min-cost-flow', '--json')
        results = json.loads(p.stdout)
        self.assertEqual([row['id'] for row in results], ['codeforces:105658'])
        self.assertIn('graph', results[0]['tags'])
        p = command('catalog.py', 'related', 'min-cost-flow', '--json')
        self.assertIn('shortest-paths', json.loads(p.stdout)['editorial'])
        # Dominators now have a local proof for the iterative-set variant.
        self.assertEqual(command('catalog.py', 'review', 'dominator-tree').returncode, 0)
        self.assertEqual(command('catalog.py', 'review', 'wavelet').returncode, 1)
        self.assertEqual(command('catalog.py', 'source', 'codeforces:105658', '--text').returncode, 1)

    def test_quality_rejects_tampering_and_alias_collisions(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'data'
            shutil.copytree(DATA, target)
            asset = target/'sources/upstream/cp-algorithms/graph/dijkstra.md.txt'
            original = asset.read_bytes()
            asset.write_bytes(original + b'local edit')
            self.assertTrue(any('modified upstream text' in x for x in check_sources(target)))
            asset.write_bytes(original)
            crosswalk = target/'knowledge/crosswalk.json'
            rows = json.loads(crosswalk.read_text(encoding='utf-8'))
            next(row for row in rows if row['id'] == 'max-flow')['aliases'].append('HLD')
            crosswalk.write_text(json.dumps(rows), encoding='utf-8')
            self.assertTrue(any('duplicate/empty canonical name' in x for x in check_sources(target)))

    def test_git_pins_ignore_worktree_and_detect_policy_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git','-C',temp,*args], encoding='utf-8').strip()
            git('init','-q')
            license_file = root/'LICENSE'
            license_file.write_text('fixture policy', encoding='utf-8')
            article = root/'src/graph/example.md'
            article.parent.mkdir(parents=True)
            article.write_text('# Fixture Graph\n\nProof.', encoding='utf-8')
            git('add','.')
            git('-c','user.name=Tester','-c','user.email=test@example.org','commit','-qm','fixture')
            provider = dict(revision=git('rev-parse','HEAD'), policy_path='LICENSE', policy_sha256=sha(license_file.read_bytes()),
                            repository='owner/repo', license='CC-BY-SA-4.0', url='https://cp-algorithms.com/', language='en', retrieved='2026-11-19')
            opts = {'cp-algorithms':['graph/example.md']}
            old, texts = records('cp-algorithms', provider, root, opts)
            article.write_text('# Changed\n', encoding='utf-8')
            self.assertEqual((old, texts), records('cp-algorithms', provider, root, opts))
            git('add','.')
            git('-c','user.name=Tester','-c','user.email=test@example.org','commit','-qm','changed')
            provider['revision'] = git('rev-parse','HEAD')
            new, _ = records('cp-algorithms', provider, root, opts)
            self.assertEqual(changes(old,new)['content_changed'], ['cp-algorithms:graph/example.md'])
            provider['policy_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError,'license declaration changed'):
                records('cp-algorithms', provider, root, opts)
            run = command('sync_catalog.py','cp-algorithms',root,'--output',root)
            self.assertEqual(run.returncode,2)
            self.assertIn('already exists',run.stderr)
