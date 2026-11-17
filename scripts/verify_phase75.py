"""Run from the repository root; isolated storage, real failures, bounded waits."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    env = dict(os.environ)
    # Deliberately retained for inspection; never touches student storage.
    env['KNOWLEDGEPILOT_STORAGE_PATH'] = tempfile.mkdtemp(prefix='knowledgepilot-verification-')
    print('Synthetic test storage:', env['KNOWLEDGEPILOT_STORAGE_PATH'], flush=True)
    node, npm = shutil.which('node'), shutil.which('npm.cmd') or shutil.which('npm')
    checks = [
        ('All backend phases and ownership tests', [sys.executable, '-m', 'pytest', 'tests', 'backend/tests', '-v', '--tb=short'], ROOT, 120),
        ('Dependency compatibility', [sys.executable, '-m', 'pip', 'check'], ROOT, 60),
        ('Frontend render/navigation checks', [node or 'node', 'test-phase7.mjs'], ROOT/'frontend', 60),
        ('Frontend auth races', [node or 'node', '--test', 'test-auth.mjs'], ROOT/'frontend', 60),
        ('Frontend production build', [npm or 'npm', 'run', 'build'], ROOT/'frontend', 120),
    ]
    failed = []
    for name, command, cwd, timeout in checks:
        print('\nCHECK:', name, flush=True)
        try:
            result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout)
            if result.returncode:
                failed.append((name, f'exit {result.returncode}'))
        except (subprocess.TimeoutExpired, OSError) as error:
            failed.append((name, str(error)))
    for name, reason in failed:
        print('FAILED/BLOCKED:', name, reason)
    return 1 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
