"""Ctrl-C while a command runs: the SIGINT handler raises KeyboardInterrupt."""

import signal

from zem.builtins.base import BaseCommand


class _Blocking(BaseCommand):
    name = "blocking_for_test"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        raise KeyboardInterrupt  # what a SIGINT does to a builtin mid-run


def test_interrupted_builtin_exits_130_and_leaves_no_state(make_headless_shell, run):
    shell = make_headless_shell(commands={"blocking_for_test": _Blocking()})
    code, _, _ = run(shell, "blocking_for_test")
    assert code == 130
    assert shell._executing == 0
    code, out, _ = run(shell, "blocking_for_test | blocking_for_test")
    assert code == 130
    assert shell._executing == 0


def test_interrupt_inside_substitution_is_contained(make_headless_shell, run):
    shell = make_headless_shell(commands={"blocking_for_test": _Blocking()})
    code, _, _ = run(shell, "blocking_for_test $(blocking_for_test)")
    assert code == 130
    assert shell._executing == 0


def test_sigint_handler_raises_only_while_executing(make_headless_shell, monkeypatch):
    shell = make_headless_shell()
    installed = {}
    monkeypatch.setattr(signal, "signal", lambda sig, fn: installed.__setitem__(sig, fn))
    shell.session = type("S", (), {"app": type("A", (), {"invalidate": lambda self: None})()})()
    shell._setup_signal_handlers()
    handler = installed[signal.SIGINT]

    handler(signal.SIGINT, None)  # at the prompt: a flag, no exception
    assert shell._interrupted is True

    shell._executing = 1
    try:
        handler(signal.SIGINT, None)
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("SIGINT during a command must raise KeyboardInterrupt")
