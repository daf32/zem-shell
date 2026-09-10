"""set / export / unset / get through the real shell."""

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for n in ("AX_L", "AX_E", "AX_INH", "AX_Q"):
        monkeypatch.delenv(n, raising=False)


# ---- set -------------------------------------------------------------------

def test_set_creates_shell_local_variable(full_shell, run):
    assert run(full_shell, "set AX_L 1")[0] == 0
    assert full_shell.context.variables["AX_L"] == "1"
    assert not full_shell.context.is_exported("AX_L")


def test_set_joins_multiple_values_with_spaces(full_shell, run):
    run(full_shell, "set AX_L a b c")
    assert full_shell.context.variables["AX_L"] == "a b c"


def test_set_export_flag(full_shell, run):
    run(full_shell, "set -x AX_E 2")
    assert full_shell.context.child_env()["AX_E"] == "2"


def test_set_erase(full_shell, run):
    run(full_shell, "set AX_L 1")
    assert run(full_shell, "set -e AX_L")[0] == 0
    assert "AX_L" not in full_shell.context.variables


def test_set_lists_variables_sorted(full_shell, run):
    run(full_shell, "set AX_L 1")
    code, out, _ = run(full_shell, "set")
    lines = out.splitlines()
    assert code == 0
    assert "AX_L=1" in lines
    assert lines == sorted(lines)


def test_set_rejects_bad_identifier_and_unknown_option(full_shell, run):
    assert run(full_shell, "set 1abc x")[0] == 2
    assert run(full_shell, "set --nope x")[0] == 2


# ---- export ----------------------------------------------------------------

def test_export_name_equals_value(full_shell, run):
    assert run(full_shell, "export AX_E=hello")[0] == 0
    assert full_shell.context.child_env()["AX_E"] == "hello"


def test_export_promotes_existing_variable(full_shell, run):
    run(full_shell, "set AX_L 1")
    assert "AX_L" not in full_shell.context.child_env()
    run(full_shell, "export AX_L")
    assert full_shell.context.child_env()["AX_L"] == "1"


def test_export_missing_name_creates_empty(full_shell, run):
    run(full_shell, "export AX_E")
    assert full_shell.context.child_env()["AX_E"] == ""


def test_export_n_unexports_but_keeps_value(full_shell, run):
    run(full_shell, "export AX_E=1")
    assert run(full_shell, "export -n AX_E")[0] == 0
    assert full_shell.context.variables["AX_E"] == "1"
    assert "AX_E" not in full_shell.context.child_env()


def test_export_listing_is_resourceable(full_shell, run):
    run(full_shell, "export AX_E=\"it's\"")
    code, out, _ = run(full_shell, "export")
    line = next(ln for ln in out.splitlines() if ln.startswith("export AX_E="))
    assert line == "export AX_E='it'\\''s'"
    # Feed it back through the parser and check the value round-trips.
    run(full_shell, "unset AX_E")
    run(full_shell, line)
    assert full_shell.context.variables["AX_E"] == "it's"


def test_export_rejects_invalid_name(full_shell, run):
    assert run(full_shell, "export 9x=1")[0] == 2


# ---- unset -----------------------------------------------------------------

def test_unset_multiple_and_unknown_is_ok(full_shell, run):
    run(full_shell, "set AX_L 1; set AX_E 2")
    assert run(full_shell, "unset AX_L AX_E AX_NOPE")[0] == 0
    assert "AX_L" not in full_shell.context.variables
    assert "AX_E" not in full_shell.context.variables


def test_unset_inherited_variable_stays_gone(full_shell, run, monkeypatch):
    monkeypatch.setenv("AX_INH", "x")
    full_shell.context.set_var("AX_INH", "x", export=True)
    run(full_shell, "unset AX_INH")
    run(full_shell, "echo next line")
    assert "AX_INH" not in full_shell.context.variables
    assert "AX_INH" not in full_shell.context.child_env()


def test_unset_rejects_question_mark_and_requires_name(full_shell, run):
    assert run(full_shell, "unset ?")[0] == 2
    assert run(full_shell, "unset")[0] == 2


# ---- get -------------------------------------------------------------------

def test_get_prints_value(full_shell, run):
    run(full_shell, "set AX_L hello")
    assert run(full_shell, "get AX_L") == (0, "hello\n", "")


def test_get_distinguishes_empty_from_unset(full_shell, run):
    run(full_shell, "set AX_L")
    assert run(full_shell, "get AX_L") == (0, "\n", "")
    code, out, err = run(full_shell, "get AX_NOPE")
    assert (code, out) == (1, "")
    assert "not set" in err


def test_get_question_mark(full_shell, run):
    run(full_shell, "get AX_NOPE")  # exit 1
    assert run(full_shell, "get ?")[1] == "1\n"


# ---- integration with children --------------------------------------------

def test_child_process_sees_exported_not_local(tmp_path, full_shell, run):
    out = tmp_path / "env"
    run(full_shell, "set AX_L 1; export AX_E=2")
    run(full_shell, f"/usr/bin/env > {out}")
    env = out.read_text()
    assert "AX_E=2" in env
    assert "AX_L=1" not in env


def test_question_mark_updates_between_units(full_shell, run):
    assert run(full_shell, "false; echo $?; true; echo $?") == (0, "1\n0\n", "")
