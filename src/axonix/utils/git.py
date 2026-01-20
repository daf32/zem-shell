"""Utilities for getting Git repository information."""
import os
import subprocess
from typing import Optional, Tuple


def get_git_info(cwd: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """
    Get Git branch and status information.
    
    Returns:
        Tuple of (branch_name, status_symbol) or None if not a git repo.
        status_symbol: '' (clean), '*' (dirty), '+' (ahead), '-' (behind)
    """
    if cwd is None:
        cwd = os.getcwd()
    
    # Check if we're in a git repository
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=cwd,
            capture_output=True,
            timeout=0.5,
            text=True
        )
        if result.returncode != 0:
            return None
        # Verify output is "true"
        if result.stdout.strip() != "true":
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    
    # Get current branch name
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=cwd,
            capture_output=True,
            timeout=0.5,
            text=True
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None
    
    # Get status symbols
    status_symbols = []
    
    # Check for uncommitted changes
    try:
        result = subprocess.run(
            ['git', 'diff', '--quiet', '--exit-code'],
            cwd=cwd,
            timeout=0.5
        )
        if result.returncode != 0:
            status_symbols.append('*')  # Dirty
    except (subprocess.TimeoutExpired, OSError):
        pass
    
    # Check for untracked files
    try:
        result = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=cwd,
            capture_output=True,
            timeout=0.5,
            text=True
        )
        if result.stdout.strip():
            status_symbols.append('*')  # Dirty
    except (subprocess.TimeoutExpired, OSError):
        pass
    
    # Check if ahead/behind remote (only if upstream is configured)
    try:
        # First check if upstream exists
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', '@{upstream}'],
            cwd=cwd,
            capture_output=True,
            timeout=0.5,
            text=True
        )
        if result.returncode == 0:
            # Upstream exists, check ahead/behind
            result = subprocess.run(
                ['git', 'rev-list', '--count', '--left-right', '@{upstream}...HEAD'],
                cwd=cwd,
                capture_output=True,
                timeout=0.5,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split('\t')
                if len(parts) == 2:
                    ahead, behind = parts
                    if int(ahead) > 0:
                        status_symbols.append('+')
                    if int(behind) > 0:
                        status_symbols.append('-')
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError):
        pass
    
    status = ''.join(sorted(set(status_symbols))) if status_symbols else ''
    
    return (branch, status)


def format_git_branch(branch: str, status: str = '', max_length: int = 20) -> str:
    """Format git branch name for display."""
    if len(branch) > max_length:
        branch = branch[:max_length-3] + '...'
    
    if status:
        return f"{branch}{status}"
    return branch
