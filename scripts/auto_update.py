"""
Auto-Update System — GitHub → Client VPS daily git pull
Runs as a scheduled task. Pulls latest code, preserves local data.
"""

import os
import sys
import subprocess
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, 'data', 'update.log')


def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')


def update():
    log("Auto-update starting...")

    # Check if we're in a git repo
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log(f"ERROR: Not a git repo or git not available: {result.stderr}")
            return False
    except Exception as e:
        log(f"ERROR: {e}")
        return False

    # Stash any local changes (shouldn't be any, but safety)
    local_changes = result.stdout.strip()
    if local_changes:
        log(f"Local changes detected ({len(local_changes.splitlines())} files) — stashing")
        subprocess.run(['git', 'stash'], cwd=ROOT, capture_output=True, timeout=30)

    # Pull latest
    pull = subprocess.run(
        ['git', 'pull', '--rebase'],
        cwd=ROOT, capture_output=True, text=True, timeout=60
    )

    if pull.returncode == 0:
        if 'Already up to date' in pull.stdout:
            log("Already up to date — no changes")
        else:
            log(f"Updated successfully:\n{pull.stdout.strip()}")
    else:
        log(f"ERROR pulling: {pull.stderr}")
        # Try to recover stash
        if local_changes:
            subprocess.run(['git', 'stash', 'pop'], cwd=ROOT, capture_output=True, timeout=30)
        return False

    # Pop stash if we stashed
    if local_changes:
        pop = subprocess.run(
            ['git', 'stash', 'pop'],
            cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        if pop.returncode != 0:
            log(f"WARNING: Stash pop conflict: {pop.stderr}")

    log("Auto-update complete")
    return True


if __name__ == '__main__':
    update()
