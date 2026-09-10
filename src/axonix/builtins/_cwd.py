"""Shared directory-changing logic for `cd`, `pushd` and `popd`."""

import os
from typing import TYPE_CHECKING

from axonix.errors.base_error import CLIError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class ChangeDirError(CLIError):
    """Raised when a directory change fails (exit code 1, bash-style text)."""

    exit_code = 1


def resolve_target(context: "ExecutionContext", cmd: str, target: str | None) -> str:
    """Turn the user-supplied argument into a path, without changing anything.

    * ``None`` -> ``$HOME`` (error if unset)
    * ``-``    -> ``$OLDPWD`` (error if unset)
    * ``~``/``~user`` prefixes are expanded
    """
    if target is None:
        home = context.variables.get("HOME")
        if not home:
            raise ChangeDirError(f"{cmd}: HOME not set")
        return home
    if target == "-":
        old = context.variables.get("OLDPWD")
        if not old:
            raise ChangeDirError(f"{cmd}: OLDPWD not set")
        return old
    if target.startswith("~"):
        return os.path.expanduser(target)
    return target


def change_directory(context: "ExecutionContext", cmd: str, path: str) -> str:
    """``chdir`` to ``path`` and update ``PWD``/``OLDPWD`` (both exported).

    Returns the new working directory. Raises :class:`ChangeDirError`
    with a bash-style message on failure.
    """
    old_pwd = os.getcwd()
    try:
        os.chdir(path)
    except FileNotFoundError:
        raise ChangeDirError(f"{cmd}: {path}: No such file or directory") from None
    except NotADirectoryError:
        raise ChangeDirError(f"{cmd}: {path}: Not a directory") from None
    except PermissionError:
        raise ChangeDirError(f"{cmd}: {path}: Permission denied") from None
    except OSError as e:
        raise ChangeDirError(f"{cmd}: {path}: {e.strerror}") from e

    # Track the *logical* path like bash does, so `cd link` keeps `link`
    # in $PWD instead of the resolved target. Fall back to the physical
    # path if the logical one doesn't actually name the new cwd.
    physical = os.getcwd()
    base = context.variables.get("PWD") or old_pwd
    logical = os.path.normpath(path if os.path.isabs(path) else os.path.join(base, path))
    new_pwd = logical if os.path.realpath(logical) == os.path.realpath(physical) else physical

    context.set_var("OLDPWD", context.variables.get("PWD") or old_pwd, export=True)
    context.set_var("PWD", new_pwd, export=True)
    return new_pwd
