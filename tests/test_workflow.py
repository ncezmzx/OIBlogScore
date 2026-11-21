import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from oiblogscore.audit import DIMENSIONS, schedule, submit
from oiblogscore.cli import main
from oiblogscore.discovery import CATEGORIES, discover
from oiblogscore.repair import repair, rollback, verify_journal
from oiblogscore.reporting import build
from oiblogscore.repository import Repo
from oiblogscore.verification import verify_pair


class Workflow(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Reviewer')
        self.git('config', 'user.email', 'reviewer@example.test')

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.root), *args], check=True, stdout=subprocess.PIPE)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
        return path

    def commit(self):
        self.git('add', '--all', '--', ':!.oiblogscore')
        self.git('commit', '-qm', 'fixture')

    def submit(self, repo, item, verdict='PASS'):
        result = self.write('.oiblogscore/result.json', json.dumps(dict(item, verdict=verdict, evidence='Checked claim and boundary against fixture constraints.')))
        submit(repo, discover(repo), result)

    def test_discovery_and_transitive_dependencies(self):
        self.write('odd location/题.md', '---\nauthor: Ada\n---\n[code](../src/foo.cpp) ![pic](../fig.svg)')
        self.write('src/foo.cpp', '#include "x.h"')
        self.write('src/x.h', 'int x;')
        self.write('fig.svg', '<svg/>')
        self.write('math/proof.tex', r'\input{appendix}')
        self.write('math/appendix.tex', r'\author{Ada}')
        self.write('front/page.mdx', '<Example />')
        self.write('other.html', '<a href="gone.md">link</a>')
        self.write('drafts/D.md', 'possibly unfinished')
        self.write('README.md', 'project')
        self.write('public/generated.html', '<main>generated</main>')
        self.write('oiblogscore.json', '{"exclude":["public/**"]}')
        self.commit()
        m = discover(Repo(self.root))
        articles = m['articles']
        a = articles['odd location/题.md']
        self.assertEqual(a['author'], 'Ada')
        self.assertEqual(a['code'], ['src/foo.cpp', 'src/x.h'])
        self.assertEqual(a['resources'], ['fig.svg'])
        self.assertEqual(articles['math/proof.tex']['resources'], ['math/appendix.tex'])
        self.assertEqual(articles['drafts/D.md']['kind'], 'draft')
        self.assertEqual(articles['README.md']['kind'], 'documentation')
        self.assertEqual(articles['front/page.mdx']['kind'], 'candidate')
        self.assertEqual(articles['other.html']['unresolved_dependencies'], [['other.html', 'gone.md']])
        self.assertEqual(m['exclusions'][0]['path'], 'public/generated.html')

    def test_resume_incremental_coverage_and_full(self):
        self.write('x.md', '# Example\n')
        self.commit()
        repo = Repo(self.root)
        m = discover(repo)
        queue = schedule(repo, m, 'full')
        self.assertEqual(len(queue), len(DIMENSIONS))
        self.submit(repo, queue[0])
        self.assertEqual(schedule(repo, m, 'resume'), queue[1:])
        self.assertEqual(build(repo, m)['verdicts']['NOT_CHECKED'], 5)
        self.assertEqual(build(repo, m)['status'], 'INCOMPLETE')
        for item in queue[1:]:
            self.submit(repo, item)
        self.assertEqual(schedule(repo, m), [])
        self.assertEqual(build(repo, m)['reviewed'], 1)
        self.assertEqual(build(repo, m)['status'], 'COMPLETE')
        self.assertNotEqual(queue[0]['ticket'], schedule(repo, m, 'full')[0]['ticket'])
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.submit(repo, queue[0])

    def test_reaudit_when_article_dependency_or_rule_changes(self):
        self.write('x.md', '[code](x.cpp)')
        self.write('x.cpp', '#include "x.h"')
        self.write('x.h', 'int x;')
        self.write('resources/reference.txt', 'rule one')
        self.commit()
        repo = Repo(self.root)
        ticket = schedule(repo, discover(repo))[0]
        for filename in ('x.h', 'x.md', 'resources/reference.txt'):
            p = self.root / filename
            self.write(filename, p.read_text() + '\nchanged')
            with self.assertRaisesRegex(ValueError, 'Stale'):
                self.submit(repo, ticket)
            new = schedule(repo, discover(repo), 'resume')[0]
            self.assertNotEqual(ticket['fingerprint'], new['fingerprint'])
            ticket = new

    def test_targeted_audit_cannot_complete_repository(self):
        self.write('notes/a.md', '动态规划')
        self.write('notes/b.tex', '动态规划')
        self.commit()
        repo = Repo(self.root)
        m = discover(repo)
        queue = schedule(repo, m, paths=['notes'], types=['md'], categories=['dp'], dimensions=['algorithm'])
        self.assertEqual([(t['path'], t['dimension']) for t in queue], [('notes/a.md', 'algorithm')])
        self.submit(repo, queue[0])
        self.assertEqual(schedule(repo, m, 'resume'), [])
        self.assertEqual(build(repo, m)['unreviewed'], 2)

    def test_categories_cover_ten_algorithm_fixtures(self):
        words = ('动态规划', '最短路', '贪心', '字符串', '数论', '线段树', '二分', '网络流', '凸包', '容斥')
        for key, word in zip(CATEGORIES, words):
            self.write(key + '.md', word)
        self.commit()
        for name, a in discover(Repo(self.root))['articles'].items():
            self.assertIn(Path(name).stem, a['categories'])

    def test_repair_exact_diff_protected_text_and_single_rollback(self):
        before = '# 我来讲线段树\r\n\r\n这个系列还会继续更行。\r\n\r\n$O(n)$，代码 `int n`。\r\n\r\n```cpp\r\n下篇再聊。。\r\n```\r\n\r\n这篇就先到写这儿吧。\r\n\r\n下次再聊这个blog 系列。'
        path = self.write('x.md', before)
        self.commit()
        repo = Repo(self.root)
        orig = discover(repo)
        queue = schedule(repo, orig)
        self.submit(repo, queue[0])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            repair(repo, orig, 'safe')
        after = path.read_bytes().decode()
        self.assertEqual(after, before.replace('继续更行', '继续更新').replace('先到写', '先写到').replace('这个blog', '这个 blog'))
        self.assertIn('--- a/x.md', out.getvalue())
        self.assertIn('+这篇就先写到这儿吧。', out.getvalue())
        self.assertNotIn('综上所述', after)
        self.assertEqual(verify_journal(repo)[0]['errors'], [])
        self.assertEqual(len(schedule(repo, discover(repo), 'resume')), len(DIMENSIONS))
        entry = repo.read('repairs.json', [])[0]
        rollback(repo, 'x.md', entry['edits'][0]['id'])
        self.assertIn('继续更行', path.read_text())
        self.assertNotIn('先到写', path.read_text())
        self.assertEqual(verify_journal(repo)[0]['errors'], [])
        rollback(repo, 'x.md')
        self.assertEqual(path.read_bytes(), before.encode())

    def test_reject_any_change_to_semantics_structure_or_protected_content(self):
        prefix = '# notes\n\n下篇再聊。。\n\n'
        cases = [('复杂度 $O(n)$', '复杂度 $O(n^2)$'), ('贪心', '动态规划'), ('```cpp\nreturn 0;\n```', '```cpp\nreturn 1;\n```'),
                 ('[代码](impl.cpp)', '[代码](missing.cpp)'), ('![图](a.svg)', '![图](b.svg)'), ('正文', '## 正文')]
        for old, new in cases:
            with self.subTest(old=old):
                self.assertTrue(verify_pair(prefix + old, prefix.replace('。。', '。') + new))
        for wrapper in ('```\n\n{}\n\n```', '$$\n\n{}\n\n$$', '<div>\n\n{}\n\n</div>'):
            self.assertTrue(verify_pair(wrapper.format('下篇再聊。。'), wrapper.format('下篇再聊。')))

    def test_good_article_dirty_file_and_same_author(self):
        good = '---\nauthor: A\n---\n# 树状数组\n\n我就用 $lowbit(x)$ 跳转，不绕弯子。\n'
        a = self.write('good.md', good)
        self.write('other.md', '---\nauthor: B\n---\n# 不同作者\n')
        bad = self.write('dirty.md', '---\nauthor: A\n---\n\n下篇再聊。。\n')
        self.commit()
        bad.write_text(bad.read_text() + '\n用户尚未提交的段落。', encoding='utf-8')
        repo = Repo(self.root)
        outcomes = repair(repo, discover(repo), 'safe')
        self.assertEqual(a.read_bytes(), good.encode())
        self.assertEqual(outcomes, [{'path': 'dirty.md', 'status': 'dirty (skipped)'}])
        self.assertEqual(repo.read('style.json', {})['dirty.md']['sources'], ['good.md'])
        self.assertIn('尚未提交', bad.read_text())

    def test_interactive_default_and_rollback_conflict(self):
        before = '# Blog\n\n下篇再聊。。\n'
        p = self.write('x.md', before)
        self.commit()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['repair', str(self.root)]), 0)
            self.assertEqual(p.read_text(), before)
            with patch('builtins.input', return_value='n'):
                self.assertEqual(main(['repair', str(self.root), '--mode', 'interactive']), 0)
                self.assertEqual(p.read_text(), before)
            self.assertEqual(main(['repair', str(self.root), '--mode', 'safe']), 0)
        repo = Repo(self.root)
        self.write('x.md', p.read_text() + '\nexternal edit')
        self.assertTrue(verify_journal(repo)[0]['errors'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            rollback(repo, 'x.md')
        self.assertIn('external edit', p.read_text())

    def test_interrupted_repair_reconciles_completed_write(self):
        before = '# Blog\n\n下篇再聊。。\n'
        p = self.write('x.md', before)
        self.commit()
        repo = Repo(self.root)
        with contextlib.redirect_stdout(io.StringIO()), patch('oiblogscore.repair.journal.reconcile', side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                repair(repo, discover(repo), 'safe')
        self.assertIn('pending', repo.read('repairs.json', [])[0])
        self.assertEqual(p.read_text(), before.replace('。。', '。'))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['resume', str(self.root)]), 0)
        self.assertEqual(verify_journal(repo)[0]['errors'], [])

    def test_committed_dependency_deletion_invalidates_cache(self):
        self.write('x.md', '[impl](x.cpp)')
        dep = self.write('x.cpp', 'int x;')
        self.commit()
        repo = Repo(self.root)
        task = schedule(repo, discover(repo))[0]
        self.submit(repo, task)
        dep.unlink()
        self.commit()
        m = discover(repo)
        self.assertEqual(m['articles']['x.md']['unresolved_dependencies'], [['x.md', 'x.cpp']])
        self.assertEqual(build(repo, m)['verdicts']['NOT_CHECKED'], 6)

    def test_manual_dependencies_and_ignore(self):
        self.write('x.md', 'no link')
        self.write('standalone.cpp', 'int x;')
        self.write('oiblogscore.json', '{"dependencies":{"x.md":["standalone.cpp"]}}')
        self.write('.gitignore', 'private/\n')
        self.write('private/secret.md', 'not in inventory')
        self.commit()
        m = discover(Repo(self.root))
        self.assertEqual(list(m['articles']), ['x.md'])
        self.assertEqual(m['articles']['x.md']['code'], ['standalone.cpp'])

    def test_git_history_can_invalidate_identical_working_bytes(self):
        body = 'original checkout bytes'
        self.write('x.md', body)
        self.commit()
        repo = Repo(self.root)
        ticket = schedule(repo, discover(repo))[0]
        self.submit(repo, ticket)
        self.write('x.md', 'different commit')
        self.commit()
        self.write('x.md', body)
        m = discover(repo)
        self.assertEqual(ticket['fingerprint'], m['articles']['x.md']['fingerprint'])
        self.assertNotEqual(ticket['ticket'], schedule(repo, m)[0]['ticket'])

    def test_untracked_and_staged_articles_never_overwritten(self):
        original = '# Notes\n\n这篇就先写到这儿。。\n'
        untracked = self.write('new.md', original)
        staged = self.write('staged.md', original)
        self.git('add', '--', 'staged.md')
        repo = Repo(self.root)
        self.assertEqual(len(repair(repo, discover(repo), 'safe')), 2)
        self.assertEqual(untracked.read_text(), original)
        self.assertEqual(staged.read_text(), original)

    def test_assume_unchanged_does_not_bypass_protection(self):
        self.write('x.md', '# Notes\n')
        self.commit()
        self.git('update-index', '--assume-unchanged', 'x.md')
        expected = '# Notes\n\n下篇再聊。。\n'
        p = self.write('x.md', expected)
        repo = Repo(self.root)
        self.assertTrue(repo.dirty('x.md'))
        repair(repo, discover(repo), 'safe')
        self.assertEqual(p.read_text(), expected)

    def test_commit_does_not_hide_pending_dimensions(self):
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        task = schedule(repo, discover(repo))[0]
        self.submit(repo, task, verdict='NOT_CHECKED')
        self.assertIn(task, schedule(repo, discover(repo), 'resume'))

    def test_invalid_findings_and_missing_rationale_rejected(self):
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        task = schedule(repo, discover(repo))[0]
        failure = dict(task, verdict='FAIL', evidence='Counterexample')
        for payload in (failure, dict(failure, verdict='PASS', evidence=' '), dict(failure, findings=[{'severity':'Major'}])):
            p = self.write('.oiblogscore/result.json', json.dumps(payload))
            with self.assertRaises(ValueError):
                submit(repo, discover(repo), p)

    def test_report_does_not_conflate_failed_with_unreviewed(self):
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        m = discover(repo)
        queue = schedule(repo, m)
        finding = dict(severity='Critical', location='line 1', message='False claim', evidence='Explicit witness')
        p = self.write('.oiblogscore/result.json', json.dumps(dict(queue[0], verdict='FAIL', evidence='Witness', findings=[finding])))
        submit(repo, m, p)
        for task in queue[1:]:
            self.submit(repo, task, verdict='NOT_APPLICABLE')
        report = build(repo, m)
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertEqual(report['severity']['Critical'], 1)
        self.assertEqual(report['verdicts']['FAIL'], 1)

    def test_staged_repair_is_not_rolled_back(self):
        original = '# Notes\n\n下篇再聊。。\n'
        p = self.write('x.md', original)
        self.commit()
        repo = Repo(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            repair(repo, discover(repo), 'safe')
        self.git('add', '--', 'x.md')
        with self.assertRaisesRegex(ValueError, 'staged'):
            rollback(repo, 'x.md')
        self.assertEqual(p.read_text(), original.replace('。。', '。'))

    def test_reserved_tracked_state_never_overwritten(self):
        p = self.write('.oiblogscore/report.md', 'user-owned file')
        self.git('add', '--', '.oiblogscore/report.md')
        with self.assertRaisesRegex(ValueError, 'Reserved'):
            Repo(self.root)
        self.assertEqual(p.read_text(), 'user-owned file')

    def test_external_reference_update_invalidates_cached_task(self):
        self.write('article.md', '# An article')
        self.commit()
        repo = Repo(self.root)
        with tempfile.TemporaryDirectory() as references, patch.dict('os.environ', {'OIBLOGSCORE_REFERENCE_ROOT': references}):
            external = Path(references)
            (external / 'skills').mkdir()
            (external / 'resources').mkdir()
            rule = external / 'resources' / 'catalog.md'
            rule.write_text('first version')
            task = schedule(repo, discover(repo))[0]
            self.submit(repo, task)
            rule.write_text('updated version')
            replacement = schedule(repo, discover(repo), 'resume')[0]
            self.assertNotEqual(task['fingerprint'], replacement['fingerprint'])

    def test_pending_context_and_unresolved_dependencies_block_completion(self):
        self.write('x.mdx', 'import Component from "./view.js"\nconst v = import(dynamicName)')
        self.write('view.js', 'export default 1')
        self.write('helper.h', 'int x;')
        self.write('oiblogscore.json', '{"dependencies":{"x.mdx":["helper.h"]}}')
        self.commit()
        repo = Repo(self.root)
        manifest = discover(repo)
        expected = {('view.js', 'heuristic'), ('helper.h', 'configured')}
        self.assertEqual({(e['target'], e['kind']) for e in manifest['articles']['x.mdx']['dependency_edges']}, expected)
        queue = schedule(repo, manifest)
        self.submit(repo, queue[0], verdict='NEEDS_CONTEXT')
        for task in queue[1:]:
            self.submit(repo, task, verdict='NOT_APPLICABLE')
        report = build(repo, manifest)
        self.assertEqual(report['verdicts']['NEEDS_CONTEXT'], 1)
        self.assertEqual(schedule(repo, manifest, 'resume'), queue[:1])
        self.submit(repo, queue[0])
        report = build(repo, manifest)
        self.assertFalse(report['completion']['audit'])
        self.assertEqual(report['articles']['x.mdx']['audit_status'], 'PENDING')
        self.assertFalse(report['completion']['discovery'])
        self.assertEqual(report['status'], 'INCOMPLETE')
        self.write('oiblogscore.json', json.dumps({'dependency_resolutions': {'x.mdx': {'import(dynamicName)': ['helper.h']}}}))
        resolved = discover(Repo(self.root))['articles']['x.mdx']
        self.assertFalse(resolved['unresolved_dependencies'])
        self.assertIn('helper.h', resolved['inputs'])
        self.assertNotEqual(resolved['fingerprint'], manifest['articles']['x.mdx']['fingerprint'])

    def test_discovery_parses_and_hashes_same_article_bytes(self):
        from hashlib import sha256
        article = self.write('x.md', '动态规划')
        self.commit()
        repo = Repo(self.root)
        real = Path.read_bytes
        calls = []

        def mutate(path):
            raw = real(path)
            # Git resolves the repository root; on Windows the fixture path
            # may still use a different spelling for the same directory.
            if path.samefile(article):
                calls.append(raw)
                article.write_bytes(b'new bytes')
            return raw

        with patch.object(Path, 'read_bytes', mutate):
            with self.assertRaisesRegex(ValueError, 'changed during discovery'):
                discover(repo)
        self.assertEqual(len(calls), 2)
        row = discover(repo)['articles']['x.md']
        self.assertEqual(row['inputs']['x.md'], sha256(b'new bytes').hexdigest())
        self.assertNotIn('dp', row['categories'])

    def test_failed_article_replace_reconciles_as_aborted(self):
        original = '# Notes\n\n下篇再聊。。\n'
        path = self.write('x.md', original)
        self.commit()
        repo = Repo(self.root)
        with contextlib.redirect_stdout(io.StringIO()), patch('oiblogscore.repair.journal.atomic', side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                repair(repo, discover(repo), 'safe')
        self.assertEqual(path.read_bytes(), original.encode())
        self.assertIn('pending', repo.read('repairs.json', [])[0])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['resume', str(self.root)]), 0)
        self.assertEqual(repo.read('repairs.json', [])[0]['status'], 'aborted')
        self.assertEqual(verify_journal(repo), [])

    def test_duplicate_configuration_key_fails_closed(self):
        self.write('oiblogscore.json', '{"exclude":[],"exclude":["*"]}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key exclude'):
            Repo(self.root)

    def test_report_renders_finding_payload_as_data(self):
        from oiblogscore.reporting import markdown
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        manifest = discover(repo)
        task = schedule(repo, manifest)[0]
        finding = dict(severity='Major', location='line 1', message='![img](https://example.test/pixel)',
                       evidence='<script>\x1b[2J</script>')
        result = self.write('.oiblogscore/result.json', json.dumps(dict(task, verdict='FAIL', evidence='witness', findings=[finding])))
        submit(repo, manifest, result)
        rendered = markdown(build(repo, manifest))
        self.assertIn('x.md:algorithm:line 1', rendered)
        self.assertNotIn('![img](', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('\x1b', rendered)

    def test_repair_git_checks_use_object_bytes_without_worktree_status(self):
        from oiblogscore.repository import git
        self.write('x.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        repo = Repo(self.root)
        with patch('oiblogscore.repository.git', wraps=git) as calls:
            self.assertFalse(repo.dirty('x.md'))
        commands = [call.args[1] for call in calls.call_args_list]
        self.assertEqual(commands, ['ls-files', 'ls-tree', 'cat-file'])
        state = {'tasks': {}, 'commit': '--output=should-not-exist'}
        repo.save('audit.json', state)
        with self.assertRaisesRegex(ValueError, 'Invalid cached audit base commit'):
            schedule(repo, discover(repo))
        self.assertFalse((self.root/'should-not-exist').exists())

    def test_dependency_literal_call_and_ambiguous_fallback(self):
        self.write('x.mdx', 'const x = import("./view.js");\n[ambiguous](appendix)')
        self.write('view.js', 'value')
        self.write('appendix.md', 'markdown')
        self.write('appendix.tex', 'latex')
        self.commit()
        row = discover(Repo(self.root))['articles']['x.mdx']
        self.assertIn('view.js', row['inputs'])
        self.assertNotIn('appendix.md', row['inputs'])
        self.assertIn(['x.mdx', 'appendix'], row['unresolved_dependencies'])

    def test_corrupt_cached_result_is_not_reported_as_pass(self):
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        task = schedule(repo, discover(repo))[0]
        self.submit(repo, task)
        state = repo.read('audit.json', {})
        state['tasks']['x.md']['algorithm']['result']['path'] = 'other.md'
        repo.save('audit.json', state)
        with self.assertRaisesRegex(ValueError, 'does not match its task'):
            build(repo, discover(repo))

    def test_failed_verify_updates_persisted_report(self):
        original = '# Notes\n\n下篇再聊。。\n'
        article = self.write('x.md', original)
        self.commit()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['repair', str(self.root), '--mode', 'safe']), 0)
        article.write_bytes((original + '用户改动\n').encode())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['verify', str(self.root)]), 1)
        report = Repo(self.root).read('report.json', {})
        self.assertFalse(report['completion']['verification'])
        self.assertEqual(report['articles']['x.md']['repair_status'], 'UNVERIFIED')
        self.assertEqual(article.read_bytes(), (original + '用户改动\n').encode())

    def test_rollback_refuses_repair_now_in_head(self):
        path = self.write('x.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        repo = Repo(self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            repair(repo, discover(repo), 'safe')
        repaired = path.read_bytes()
        self.commit()
        with self.assertRaisesRegex(ValueError, 'HEAD'):
            rollback(repo, 'x.md')
        self.assertEqual(path.read_bytes(), repaired)

    def test_edit_during_temp_file_flush_does_not_get_overwritten(self):
        from os import fsync
        path = self.write('x.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        repo = Repo(self.root)
        original = path.read_bytes()
        calls = []
        def edit(fd):
            fsync(fd)
            calls.append(fd)
            if len(calls) == 2:  # pending journal was first; article temp file second
                path.write_bytes(original + b'external edit\n')
        with contextlib.redirect_stdout(io.StringIO()), patch('oiblogscore.repository.os.fsync', side_effect=edit):
            with self.assertRaisesRegex(ValueError, 'changed before write'):
                repair(repo, discover(repo), 'safe')
        self.assertEqual(path.read_bytes(), original + b'external edit\n')

    def test_repair_fsync_replace_and_final_journal_faults(self):
        import errno
        from os import fsync, replace
        for operation, real in [('fsync', fsync), ('replace', replace)]:
            with self.subTest(operation=operation):
                name = operation + '.md'
                path = self.write(name, '# Notes\n\n下篇再聊。。\n')
                self.commit()
                repo = Repo(self.root)
                original = path.read_bytes()
                calls = []
                def fail_second(*args):
                    calls.append(args)
                    if len(calls) == 2:
                        raise OSError(errno.ENOSPC, 'fixture fault')
                    return real(*args)
                with contextlib.redirect_stdout(io.StringIO()), patch('oiblogscore.repository.os.' + operation, side_effect=fail_second):
                    with self.assertRaises(OSError):
                        repair(repo, discover(repo), 'safe', [name])
                self.assertEqual(path.read_bytes(), original)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['resume', str(self.root)]), 0)
                self.assertEqual(repo.read('repairs.json', [])[-1]['status'], 'aborted')
        path = self.write('final.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        repo = Repo(self.root)
        save = repo.save
        def fail_final(name, value):
            if name == 'repairs.json' and value[-1]['status'] == 'applied':
                raise OSError(errno.ENOSPC, 'fixture final journal fault')
            return save(name, value)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(repo, 'save', side_effect=fail_final):
            with self.assertRaises(OSError):
                repair(repo, discover(repo), 'safe', ['final.md'])
        self.assertIn('下篇再聊。\n'.encode(), path.read_bytes())
        self.assertIn('pending', repo.read('repairs.json', [])[-1])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['resume', str(self.root)]), 0)
        self.assertEqual(repo.read('repairs.json', [])[-1]['status'], 'applied')

    def test_damaged_pending_journal_does_not_reconcile_or_write(self):
        path = self.write('x.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        repo = Repo(self.root)
        original = path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()), patch('oiblogscore.repair.journal.atomic', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                repair(repo, discover(repo), 'safe')
        journal = repo.read('repairs.json', [])
        journal[-1]['pending']['update']['edits'][0]['line'] = 0
        repo.save('repairs.json', journal)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['resume', str(self.root)]), 2)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(repo.read('repairs.json', []), journal)

    def test_autocrlf_worktree_difference_is_not_silently_repaired(self):
        self.git('config', 'core.autocrlf', 'true')
        path = self.write('论文.md', '# Notes\n\n下篇再聊。。\n')
        self.commit()
        crlf = path.read_bytes().replace(b'\n', b'\r\n')
        path.write_bytes(crlf)
        repo = Repo(self.root)
        self.assertTrue(repo.dirty('论文.md'))
        with contextlib.redirect_stdout(io.StringIO()):
            repair(repo, discover(repo), 'safe')
        self.assertEqual(path.read_bytes(), crlf)
        self.assertEqual(repo.read('repairs.json', []), [])

    def test_repo_path_refuses_nonportable_names(self):
        repo = Repo(self.root)
        for value in ('C:notes.md', 'C:/notes.md', r'\\server\share\notes.md', r'dir\x.md',
                      'AUX.md', 'name. ', '../x.md', '.GiT/config'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                repo.path(value)
        self.assertEqual(repo.path('目录/文章.md').relative_to(repo.root).as_posix(), '目录/文章.md')

    def test_report_authority_changes_when_audit_updates(self):
        self.write('x.md', 'text')
        self.commit()
        repo = Repo(self.root)
        manifest = discover(repo)
        before = build(repo, manifest)['authority_sha256']
        schedule(repo, manifest)
        after = build(repo, manifest)['authority_sha256']
        self.assertNotEqual(before['audit.json'], after['audit.json'])
        self.assertEqual(before['repairs.json'], after['repairs.json'])
        self.assertEqual(after, build(repo, manifest)['authority_sha256'])
