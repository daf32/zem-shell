"""Smoke tests for the shared fixtures in conftest.py."""

from zem.builtins.base import BaseCommand
from zem.builtins.registry import CommandRegistry


def test_full_shell_has_real_builtins_only(full_shell):
    assert "cd" in full_shell.commands
    assert "help" in full_shell.commands
    assert "techo" not in full_shell.commands  # test_executor's local builtin
    assert "add" not in full_shell.commands    # removed test builtin


def test_headless_shell_has_no_commands(headless_shell):
    assert headless_shell.commands == {}


def test_run_helper_captures_output_and_exit_code(full_shell, run):
    code, out, err = run(full_shell, "echo hello")
    assert (code, out) == (0, "hello\n")


def test_registry_isolation_part_one():
    class _Leaky(BaseCommand):
        name = "tleaky"

        def execute(self, args, context, stdin=None, stdout=None):
            return 0

    assert "tleaky" in CommandRegistry.get_command_names()


def test_registry_isolation_part_two():
    # The class defined in the previous test must not survive into this one.
    assert "tleaky" not in CommandRegistry.get_command_names()
