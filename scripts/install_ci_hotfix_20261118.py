#!/usr/bin/env python3
"""Safely update BVT Studio GitHub Actions CI after water QA v0.2.1.

Only edits .github/workflows/check.yml; does not touch Blender, YOLO or tests.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'check.yml'
OLD = """name: source-checks
on:
  push:
  pull_request:
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Static tests
        run: python -m unittest discover -s tests -v
      - name: Build Blender legacy addon ZIP
        run: python scripts/build_addon.py
      - name: Upload installable ZIP
        uses: actions/upload-artifact@v4
        with:
          name: BVT_Studio_Blender_Addon_v0.2
          path: dist/BVT_Studio_Blender_Addon_v0.2.zip
"""
NEW = """name: source-checks
on:
  push:
  pull_request:
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install test dependencies
        run: python -m pip install numpy==2.2.6
      - name: Static and numerical tests
        run: python -m unittest discover -s tests -v
      - name: Build Blender addon ZIP
        run: python scripts/build_addon.py
      - name: Upload installable ZIP
        uses: actions/upload-artifact@v4
        with:
          name: BVT_Studio_Blender_Addon
          path: dist/BVT_Studio_Blender_Addon_*.zip
          if-no-files-found: error
"""

def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def main() -> int:
    if git('branch', '--show-current') != 'feature/photorealistic-droplets-v05':
        raise RuntimeError('Wrong branch; expected feature/photorealistic-droplets-v05')
    if subprocess.call(['git', 'merge-base', '--is-ancestor',
                        'c0547cc8a1c75a424530d19d7540713b94c209f6', 'HEAD'],
                       cwd=ROOT) != 0:
        raise RuntimeError('Base commit c0547cc not found in local HEAD ancestry')
    if not WORKFLOW.is_file():
        raise RuntimeError('Workflow file missing: ' + str(WORKFLOW))
    before = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    if before == NEW:
        print('CI_HOTFIX=ALREADY_APPLIED')
        return 0
    if before != OLD:
        raise RuntimeError('Unknown workflow changes; refusing to overwrite. Review .github/workflows/check.yml')
    # Only the workflow path must be clean; users may have unrelated untracked files.
    if git('status', '--porcelain', '--', '.github/workflows/check.yml'):
        raise RuntimeError('Workflow has local modifications; refusing overwrite')
    backup = ROOT / 'qa_renders' / 'patch_backups' / 'check_yml_before_ci_hotfix_20261118.yml'
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_text(before, encoding='utf-8', newline='\n')
    WORKFLOW.write_text(NEW, encoding='utf-8', newline='\n')
    assert 'numpy==2.2.6' in WORKFLOW.read_text(encoding='utf-8')
    print('CI_HOTFIX=OK')
    print('CHANGED=.github/workflows/check.yml')
    print('BACKUP=' + str(backup))
    print('NOTE=CI must be rerun on GitHub; local Blender tests do not prove CI green')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('CI_HOTFIX=FAILED:', str(exc), file=sys.stderr)
        sys.exit(2)
