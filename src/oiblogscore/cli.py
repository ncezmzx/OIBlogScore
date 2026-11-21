"""Command-line interface; no implicit Agent or code execution."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from .audit import DIMENSIONS, schedule, submit
from .discovery import CATEGORIES, discover
from .repair import reconcile, repair, rollback, verify_journal
from .reporting import build, markdown
from .repository import Repo, atomic


def parser():
    p = argparse.ArgumentParser(prog='oiblogscore', description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('scan', 'audit', 'resume', 'submit', 'repair', 'verify', 'report', 'rollback'):
        c = sub.add_parser(command)
        c.add_argument('repository', nargs='?', default='.')
        if command in ('audit', 'repair'):
            c.add_argument('--path', action='append', default=[], help='repo-relative file or directory (repeatable)')
        if command == 'audit':
            modes = c.add_mutually_exclusive_group()
            modes.add_argument('--full', action='store_true')
            modes.add_argument('--incremental', action='store_true', help='default: reuse valid results')
            c.add_argument('--type', action='append', default=[])
            c.add_argument('--category', action='append', choices=CATEGORIES, default=[])
            c.add_argument('--dimension', action='append', choices=DIMENSIONS, default=[])
        if command == 'submit':
            c.add_argument('--result', required=True, type=Path)
        if command == 'repair':
            c.add_argument('--mode', choices=('audit-only', 'safe', 'interactive'), default='audit-only')
        if command == 'rollback':
            c.add_argument('--path', required=True)
            c.add_argument('--edit-id')
        if command == 'report':
            c.add_argument('--json', action='store_true')
    return p


def _utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except (AttributeError, OSError):
            pass


def main(argv=None):
    _utf8_stdio()
    args = parser().parse_args(argv)
    try:
        repo = Repo(args.repository)
        command = args.command
        exit_code = 0
        with repo.lock():
            paths = getattr(args, 'path', [])
            if isinstance(paths, str):
                paths = [paths]
            for path in paths:
                repo.path(path)
            paths = [repo.path(path).relative_to(repo.root).as_posix() for path in paths]
            manifest = discover(repo)
            if command == 'audit' or command == 'repair' and args.mode == 'audit-only':
                queue = schedule(repo, manifest, 'full' if getattr(args, 'full', False) else 'incremental', paths,
                                 [x.lower().lstrip('.') for x in getattr(args, 'type', [])], getattr(args, 'category', []),
                                 getattr(args, 'dimension', []) or DIMENSIONS)
                print('{} pending tasks: .oiblogscore/queue.json'.format(len(queue)))
            elif command == 'resume':
                reconcile(repo, repo.read('repairs.json', []))
                print('{} pending tasks'.format(len(schedule(repo, manifest, 'resume'))))
            elif command == 'submit':
                submit(repo, manifest, args.result)
                schedule(repo, manifest, 'resume')
            elif command in ('repair', 'rollback'):
                if command == 'repair':
                    repair(repo, manifest, args.mode, paths)
                else:
                    print(rollback(repo, paths[0], args.edit_id), end='')
                manifest = discover(repo)
                schedule(repo, manifest)
            elif command == 'verify':
                checks = verify_journal(repo)
                if not checks:
                    print('No active or interrupted repairs to verify; this does not certify article correctness.',
                          file=sys.stderr)
                print(json.dumps(checks, ensure_ascii=False, indent=2))
                if any(check['errors'] for check in checks):
                    exit_code = 1
            report = build(repo, manifest)
            repo.save('manifest.json', {**manifest, 'articles': {name: {key: value for key, value in article.items() if key != 'results'} for name, article in report['articles'].items()}})
            repo.save('report.json', report)
            view = markdown(report)
            atomic(repo.path('.oiblogscore/report.md'), view.encode())
            if command == 'report':
                print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else view, end='\n')
            elif command == 'scan':
                print('{} candidates: .oiblogscore/manifest.json'.format(report['discovered']))
        return exit_code
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode('utf-8', errors='replace').strip() if isinstance(exc.stderr, bytes) else str(exc)
        print('oiblogscore: git failed: {}'.format(detail), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        print('oiblogscore: {}'.format(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
