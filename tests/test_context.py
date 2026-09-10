"""Variable / environment model of ExecutionContext."""

import os

import pytest

from axonix.core.context import ExecutionContext


@pytest.fixture
def ctx(monkeypatch):
    """Hermetic context: explicit variables, nothing from the real environ.

    `os.environ` mutations made through the context are undone by
    monkeypatch at teardown.
    """
    for name in ("AX_A", "AX_B", "AX_NEW", "AX_INH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AX_INH", "inherited")
    return ExecutionContext(variables={"AX_INH": "inherited", "PATH": "/bin"})


def test_explicit_variables_are_hermetic(ctx):
    assert set(ctx.variables) == {"AX_INH", "PATH"}
    assert ctx.exported == {"AX_INH", "PATH"}
    assert ctx.child_env() == {"AX_INH": "inherited", "PATH": "/bin"}


def test_default_context_seeds_from_environ(monkeypatch):
    monkeypatch.setenv("AX_SEED", "1")
    c = ExecutionContext()
    assert c.variables["AX_SEED"] == "1"
    assert c.is_exported("AX_SEED")


def test_set_new_var_is_shell_local(ctx):
    ctx.set_var("AX_NEW", "x")
    assert ctx.variables["AX_NEW"] == "x"
    assert not ctx.is_exported("AX_NEW")
    assert "AX_NEW" not in ctx.child_env()
    assert "AX_NEW" not in os.environ


def test_set_inherited_var_stays_exported(ctx):
    ctx.set_var("AX_INH", "changed")
    assert ctx.is_exported("AX_INH")
    assert ctx.child_env()["AX_INH"] == "changed"
    assert os.environ["AX_INH"] == "changed"


def test_export_promotes_and_mirrors(ctx):
    ctx.set_var("AX_A", "1")
    ctx.export_var("AX_A")
    assert ctx.child_env()["AX_A"] == "1"
    assert os.environ["AX_A"] == "1"


def test_export_creates_empty_if_missing(ctx):
    ctx.export_var("AX_B")
    assert ctx.variables["AX_B"] == ""
    assert os.environ["AX_B"] == ""


def test_set_with_export_flag(ctx):
    ctx.set_var("AX_A", "1", export=True)
    assert os.environ["AX_A"] == "1"
    ctx.set_var("AX_A", "2", export=False)
    assert ctx.variables["AX_A"] == "2"
    assert "AX_A" not in os.environ
    assert "AX_A" not in ctx.child_env()


def test_unexport_keeps_value(ctx):
    ctx.unexport_var("AX_INH")
    assert ctx.variables["AX_INH"] == "inherited"
    assert "AX_INH" not in ctx.child_env()
    assert "AX_INH" not in os.environ


def test_unset_removes_everywhere(ctx):
    ctx.unset_var("AX_INH")
    assert "AX_INH" not in ctx.variables
    assert "AX_INH" not in ctx.exported
    assert "AX_INH" not in os.environ
    ctx.unset_var("AX_NOPE")  # unknown name is a no-op


def test_question_mark_is_never_exported(ctx):
    ctx.last_exit_code = 7
    assert ctx.variables["?"] == "7"
    assert not ctx.is_exported("?")
    assert "?" not in ctx.child_env()
    assert os.environ.get("?") is None


def test_exit_status_defaults_to_zero():
    assert ExecutionContext(variables={}).exit_status == 0
