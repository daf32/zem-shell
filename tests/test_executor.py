"""Tests for CommandExecutor and Shell._execute_pipeline.

These tests construct a headless Shell so the real prompt-toolkit / TTY
plumbing is skipped; the parser → executor → pipeline path is exercised
end-to-end.
"""

from __future__ import annotations


import pytest

from axonix.builtins.base import BaseCommand
from axonix.core.context import ExecutionContext
from axonix.core.executor import CommandExecutor
from axonix.errors.input_error import UnknownCommandError


# --------------------------------------------------------------------------
# Tiny test builtins. They live here so they don't get auto-registered
# into the global CommandRegistry — we hand them to Shell() directly.
# --------------------------------------------------------------------------

class _EchoBuiltin(BaseCommand):
    """A toy `echo` that joins args with spaces and writes to stdout.
    Defined locally to avoid touching the global CommandRegistry."""
    name = "techo"

    def execute(self, args, context, stdin=None, stdout=None):
        self._write(" ".join(args) + "\n", stdout)
        return 0


class _FailBuiltin(BaseCommand):
    """Always exits with code 7."""
    name = "tfail"

    def execute(self, args, context, stdin=None, stdout=None):
        return 7


class _PassThruBuiltin(BaseCommand):
    """Reads stdin, writes to stdout. Used to verify pipeline plumbing."""
    name = "tcat"

    def execute(self, args, context, stdin=None, stdout=None):
        text = self._read_stdin_all(stdin)
        self._write(text, stdout)
        return 0


@pytest.fixture
def builtins_for_pipeline():
    """A small map of test builtins keyed by name.

    Locally-defined classes still call `BaseCommand.__init_subclass__`,
    which auto-registers them in the global CommandRegistry. That's
    harmless for these tests but we hand back fresh instances scoped to
    each call.
    """
    return {
        "techo": _EchoBuiltin(),
        "tfail": _FailBuiltin(),
        "tcat": _PassThruBuiltin(),
    }


# --------------------------------------------------------------------------
# CommandExecutor unit tests
# --------------------------------------------------------------------------

def test_builtin_thread_carries_exit_code():
    """`execute_builtin` stashes return value on `thread.exit_code` and
    does NOT mutate context.last_exit_code (P1-7)."""
    ctx = ExecutionContext()
    ex = CommandExecutor(ctx)

    t = ex.execute_builtin(_FailBuiltin(), [])
    t.join(timeout=2)
    assert t.exit_code == 7
    # Worker must NOT have written to the shared context attribute.
    assert ctx.last_exit_code == 0


def test_builtin_returning_none_maps_to_zero():
    """Legacy builtins returning None → exit_code 0 (backward compat)."""
    class _Legacy(BaseCommand):
        name = "tlegacy"
        def execute(self, args, context, stdin=None, stdout=None):
            return None

    ctx = ExecutionContext()
    ex = CommandExecutor(ctx)
    t = ex.execute_builtin(_Legacy(), [])
    t.join(timeout=2)
    assert t.exit_code == 0


def test_builtin_cli_error_maps_to_exit_code():
    """Raising a CLIError surfaces its exit_code via thread.exit_code."""
    from axonix.errors.input_error import ArgumentError

    class _Raises(BaseCommand):
        name = "traises"
        def execute(self, args, context, stdin=None, stdout=None):
            raise ArgumentError("traises", args, "bad")

    ctx = ExecutionContext()
    ex = CommandExecutor(ctx)
    t = ex.execute_builtin(_Raises(), ["x"])
    t.join(timeout=2)
    # ArgumentError → InputError.exit_code == 2
    assert t.exit_code == 2


def test_external_missing_command_raises_unknown_command_error():
    """`execute_external` for a non-existent binary surfaces
    UnknownCommandError (P0-5), not a generic OSError."""
    ex = CommandExecutor(ExecutionContext())
    with pytest.raises(UnknownCommandError):
        ex.execute_external("nope-cmd-xyz-not-real", [])


def test_external_real_binary_runs():
    """Sanity: a real binary returns a Popen and exits cleanly."""
    ex = CommandExecutor(ExecutionContext())
    proc = ex.execute_external("/usr/bin/true", [])
    assert proc.wait() == 0


# --------------------------------------------------------------------------
# Pipeline-level tests through Shell._execute_pipeline
# --------------------------------------------------------------------------

def test_single_builtin_pipeline_sets_exit_code(make_headless_shell, builtins_for_pipeline):
    """`tfail` alone → context.last_exit_code becomes 7."""
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line("tfail")
    assert shell.context.last_exit_code == 7


def test_builtin_pipeline_uses_last_stage_exit_code(make_headless_shell, builtins_for_pipeline):
    """`tfail | techo hi` → echo wins (exit 0), not tfail (exit 7).
    Verifies P1-7: race-free pipeline exit code."""
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line("tfail | techo hi")
    assert shell.context.last_exit_code == 0


def test_logical_and_short_circuits_on_failure(make_headless_shell, builtins_for_pipeline):
    """`tfail && techo unreached` shouldn't reach echo."""
    shell = make_headless_shell(commands=builtins_for_pipeline)
    # If echo *did* run, it'd push exit_code back to 0. We expect 7.
    shell._execute_line("tfail && techo unreached")
    assert shell.context.last_exit_code == 7


def test_logical_or_short_circuits_on_success(make_headless_shell, builtins_for_pipeline):
    """`techo ok || tfail` → tfail not run, exit 0."""
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line("techo ok || tfail")
    assert shell.context.last_exit_code == 0


def test_redirect_stdout_to_file(tmp_path, make_headless_shell, builtins_for_pipeline):
    """`techo hello > <file>` writes to the named file."""
    out = tmp_path / "out.txt"
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line(f"techo hello > {out}")
    assert out.read_text() == "hello\n"


def test_redirect_append_to_file(tmp_path, make_headless_shell, builtins_for_pipeline):
    out = tmp_path / "out.txt"
    out.write_text("before\n")
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line(f"techo hello >> {out}")
    assert out.read_text() == "before\nhello\n"


def test_pipeline_pipes_data_between_builtins(tmp_path, make_headless_shell, builtins_for_pipeline):
    """`techo abc | tcat > <file>` — echo's stdout reaches cat's stdin
    via os.pipe, then cat writes to the redirected file."""
    out = tmp_path / "out.txt"
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line(f"techo abc | tcat > {out}")
    assert out.read_text() == "abc\n"


def test_unknown_external_command_sets_error_exit_code(make_headless_shell, builtins_for_pipeline):
    """A typo doesn't crash the shell; exit_code reflects the error."""
    shell = make_headless_shell(commands=builtins_for_pipeline)
    shell._execute_line("nope-cmd-xyz-not-real")
    # UnknownCommandError → exit_code 2
    assert shell.context.last_exit_code == 2
