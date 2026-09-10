"""test / [ — evaluator unit tests plus shell integration."""

import pytest

from zem.builtins._test_expr import ExprSyntaxError, evaluate


@pytest.fixture
def files(tmp_path):
    (tmp_path / "f").write_text("data")
    (tmp_path / "empty").write_text("")
    (tmp_path / "d").mkdir()
    (tmp_path / "ln").symlink_to(tmp_path / "f")
    return tmp_path


@pytest.mark.parametrize("expr, expected", [
    ([], False),
    ([""], False),
    (["x"], True),
    (["-z", ""], True),
    (["-z", "a"], False),
    (["-n", "a"], True),
    (["-n", ""], False),
    (["a", "=", "a"], True),
    (["a", "==", "b"], False),
    (["a", "!=", "b"], True),
    (["a", "<", "b"], True),
    (["b", ">", "a"], True),
    (["3", "-eq", "3"], True),
    (["3", "-ne", "3"], False),
    (["2", "-lt", "3"], True),
    (["3", "-le", "3"], True),
    (["4", "-gt", "3"], True),
    (["3", "-ge", "4"], False),
    (["!", "a", "=", "b"], True),
    (["!", "!", "x"], True),
    (["a", "=", "a", "-a", "b", "=", "b"], True),
    (["a", "=", "a", "-a", "b", "=", "c"], False),
    (["a", "=", "b", "-o", "b", "=", "b"], True),
    (["(", "a", "=", "b", ")", "-o", "x"], True),
    (["-n", "=", "-n"], True),            # binary wins over unary flag
])
def test_evaluate_table(expr, expected):
    assert evaluate(expr) is expected


def test_file_tests(files):
    f, e, d, ln = (str(files / n) for n in ("f", "empty", "d", "ln"))
    assert evaluate(["-e", f]) and evaluate(["-f", f]) and not evaluate(["-d", f])
    assert evaluate(["-d", d]) and not evaluate(["-f", d])
    assert evaluate(["-s", f]) and not evaluate(["-s", e])
    assert evaluate(["-L", ln]) and evaluate(["-h", ln]) and not evaluate(["-L", f])
    assert evaluate(["-r", f]) and evaluate(["-w", f])
    assert not evaluate(["-e", str(files / "nope")])


def test_lone_operator_is_a_nonempty_string():
    assert evaluate(["-eq"]) is True  # coreutils agrees


@pytest.mark.parametrize("expr", [
    ["1", "-eq"],
    ["a", "-eq", "1"],
    ["(", "x"],
    ["a", "=", "b", "c"],
    ["-q", "x"],
])
def test_syntax_errors(expr):
    with pytest.raises(ExprSyntaxError):
        evaluate(expr)


def test_shell_test_and_bracket(full_shell, run):
    assert run(full_shell, "test 1 -eq 1")[0] == 0
    assert run(full_shell, "test 1 -eq 2")[0] == 1
    assert run(full_shell, "[ a = a ]")[0] == 0
    assert run(full_shell, "[ a = b ] || echo no") == (0, "no\n", "")
    code, _, err = run(full_shell, "[ a = a")
    assert code == 2 and "missing ']'" in err
    code, _, err = run(full_shell, "test a -eq 1")
    assert code == 2 and "integer expression" in err


def test_shell_test_with_variables(full_shell, run):
    run(full_shell, "set X hello")
    assert run(full_shell, '[ "$X" = hello ] && echo yes') == (0, "yes\n", "")
    assert run(full_shell, '[ -z "$UNSET_VAR_XYZ" ] && echo empty') == (0, "empty\n", "")
