import pytest

from axonix.config.settings import AppConfig
from axonix.core.parser import Parser
from axonix.errors.parser_error import ParseError


def test_pipe_requires_command():
    cfg = AppConfig()
    parser = Parser("echo hi | ", {}, {}, cfg)
    with pytest.raises(ParseError):
        parser.parse()


def test_quotes_and_variables():
    cfg = AppConfig()
    parser = Parser("echo \"hello $NAME\" 'raw $NAME'", {"NAME": "world"}, {}, cfg)
    units = parser.parse()
    assert units[0]["pipeline"][0]["name"] == "echo"
    assert units[0]["pipeline"][0]["args"] == ["hello world", "raw $NAME"]


def test_alias_expansion_single_pass():
    cfg = AppConfig()
    aliases = {"ll": "echo hi"}
    parser = Parser("ll", {}, aliases, cfg)
    units = parser.parse()
    assert units[0]["pipeline"][0]["name"] == "echo"
    assert units[0]["pipeline"][0]["args"] == ["hi"]


def test_redirections():
    cfg = AppConfig()
    parser = Parser("echo hello > out.txt", {}, {}, cfg)
    units = parser.parse()
    cmd = units[0]["pipeline"][0]
    assert cmd["name"] == "echo"
    assert cmd["stdout_file"] == "out.txt"
    assert cmd["append"] is False

    parser = Parser("cat < in.txt >> out.txt", {}, {}, cfg)
    units = parser.parse()
    cmd = units[0]["pipeline"][0]
    assert cmd["name"] == "cat"
    assert cmd["stdin_file"] == "in.txt"
    assert cmd["stdout_file"] == "out.txt"
    assert cmd["append"] is True


def _args(line: str, variables=None, aliases=None) -> list[str]:
    cfg = AppConfig()
    units = Parser(line, variables or {}, aliases or {}, cfg).parse()
    cmd = units[0]["pipeline"][0]
    return [cmd["name"], *cmd["args"]]


def test_escaped_single_quote_outside_quotes():
    assert _args(r"echo a\'b") == ["echo", "a'b"]


def test_escaped_double_quote_inside_double_quotes():
    assert _args(r'echo "a\"b"') == ["echo", 'a"b']


def test_single_quote_splice_idiom():
    # 'it'\''s' is how re-sourceable listings embed a single quote.
    assert _args(r"echo 'it'\''s'") == ["echo", "it's"]


def test_escaped_dollar_is_literal():
    assert _args(r"echo \$HOME", {"HOME": "/h"}) == ["echo", "$HOME"]


def test_escaped_space_joins_token():
    assert _args(r"echo a\ b") == ["echo", "a b"]


def test_backslash_inside_single_quotes_is_literal():
    assert _args(r"echo 'a\b'") == ["echo", "a\\b"]


# ---------------------------------------------------------------------------
# Broad coverage of the interactive syntax
# ---------------------------------------------------------------------------

def _parse(line: str, variables=None, aliases=None):
    return Parser(line, variables or {}, aliases or {}, AppConfig()).parse()


def _cmd(line: str, **kw) -> dict:
    return _parse(line, **kw)[0]["pipeline"][0]


# -- words, quoting, variables -------------------------------------------

def test_whitespace_collapses_between_words():
    assert _args("echo   a \t b") == ["echo", "a", "b"]


def test_adjacent_quoted_and_unquoted_join():
    assert _args("""echo a'b'"c"d""") == ["echo", "abcd"]


def test_empty_quotes_make_empty_argument():
    assert _args("echo '' \"\"") == ["echo", "", ""]


def test_unclosed_quote_raises():
    with pytest.raises(ParseError):
        _parse("echo 'oops")


def test_braced_variable_and_adjacent_text():
    assert _args("echo ${X}y", {"X": "1"}) == ["echo", "1y"]


def test_unset_variable_expands_to_empty():
    assert _args("echo a$NOPE.b") == ["echo", "a.b"]


def test_question_mark_variable():
    assert _args("echo $?", {"?": "7"}) == ["echo", "7"]


def test_variable_in_double_quotes_only():
    assert _args("""echo "$X" '$X'""", {"X": "v"}) == ["echo", "v", "$X"]


def test_variable_value_is_not_word_split():
    # Unlike bash: expansions stay one word (fish semantics).
    assert _args("echo $X", {"X": "a b"}) == ["echo", "a b"]


def test_comment_char_is_ordinary_text():
    # `#` has no comment meaning inside a command line (only the rc loader
    # skips whole-line comments).
    assert _args("echo a#b") == ["echo", "a#b"]


# -- logic and pipes ---------------------------------------------------

def test_pipeline_split_and_names():
    units = _parse("a | b | c")
    assert [c["name"] for c in units[0]["pipeline"]] == ["a", "b", "c"]


def test_logic_operators_attach_to_preceding_unit():
    units = _parse("a && b || c ; d")
    assert [(u["pipeline"][0]["name"], u["logic"]) for u in units] == [
        ("a", "&&"), ("b", "||"), ("c", ";"), ("d", None)
    ]


def test_or_is_not_two_pipes():
    units = _parse("a || b")
    assert len(units) == 2 and len(units[0]["pipeline"]) == 1


def test_operators_inside_quotes_are_literal():
    assert _args("echo 'a | b && c ; d'") == ["echo", "a | b && c ; d"]


def test_empty_command_between_operators_raises():
    with pytest.raises(ParseError):
        _parse("a && && b")


def test_leading_semicolon_is_ignored():
    assert _parse("; a")[0]["pipeline"][0]["name"] == "a"


def test_trailing_semicolon_is_ok():
    assert len(_parse("a;")) == 1


def test_only_whitespace_raises():
    with pytest.raises(ParseError):
        _parse("   ")


# -- background --------------------------------------------------------

def test_background_marks_last_stage_only():
    units = _parse("a | b &")
    assert [c["background"] for c in units[0]["pipeline"]] == [False, True]


def test_background_in_middle_unit():
    units = _parse("a & b")
    # `&` is not a separator today: it only flags the pipeline.
    assert units[0]["pipeline"][0]["background"] is True


# -- aliases -----------------------------------------------------------

def test_alias_with_parameters_consumes_and_passes_rest():
    aliases = {"gc": "git commit -m $1"}
    assert _args("gc msg extra", aliases=aliases) == ["git", "commit", "-m", "msg", "extra"]


def test_alias_missing_parameter_is_empty():
    aliases = {"two": "echo $1 $2"}
    assert _args("two a", aliases=aliases) == ["echo", "a"]


def test_alias_chain_and_cycle_stops():
    aliases = {"a": "b", "b": "a"}
    assert _args("a x", aliases=aliases) == ["a", "x"]


def test_alias_only_expands_in_command_position():
    aliases = {"ll": "ls -l"}
    assert _args("echo ll", aliases=aliases) == ["echo", "ll"]


# -- globs -------------------------------------------------------------

def test_glob_expands_and_sorts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for n in ("b.txt", "a.txt", "c.md"):
        (tmp_path / n).write_text("")
    assert _args("ls *.txt") == ["ls", "a.txt", "b.txt"]


def test_quoted_glob_is_literal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("")
    assert _args("ls '*.txt'") == ["ls", "*.txt"]


def test_glob_without_match_stays_literal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _args("ls *.zzz") == ["ls", "*.zzz"]


# -- tilde -------------------------------------------------------------

def test_tilde_expands_to_home(monkeypatch):
    monkeypatch.setenv("HOME", "/h")
    assert _args("cd ~") == ["cd", "/h"]
    assert _args("ls ~/x/y") == ["ls", "/h/x/y"]


def test_tilde_quoted_or_inside_word_is_literal(monkeypatch):
    monkeypatch.setenv("HOME", "/h")
    assert _args("echo '~' a~b") == ["echo", "~", "a~b"]


def test_tilde_unknown_user_is_literal():
    assert _args("echo ~no_such_user_xyz/x") == ["echo", "~no_such_user_xyz/x"]


def test_tilde_in_redirect_target(monkeypatch):
    monkeypatch.setenv("HOME", "/h")
    assert _cmd("echo > ~/out")["stdout_file"] == "/h/out"


# -- redirections ------------------------------------------------------

def test_stderr_redirect_forms():
    c = _cmd("cmd 2> err")
    assert (c["stderr_file"], c["stderr_append"], c["args"]) == ("err", False, [])
    c = _cmd("cmd 2>> err")
    assert (c["stderr_file"], c["stderr_append"]) == ("err", True)


def test_stderr_to_stdout():
    c = _cmd("cmd > out 2>&1")
    assert c["stdout_file"] == "out" and c["stderr_to_stdout"] is True
    assert c["stderr_file"] is None and c["args"] == []


def test_ampersand_redirect_both():
    c = _cmd("cmd &> both")
    assert (c["stdout_file"], c["append"], c["stderr_to_stdout"]) == ("both", False, True)
    assert c["background"] is False
    c = _cmd("cmd &>> both")
    assert (c["stdout_file"], c["append"], c["stderr_to_stdout"]) == ("both", True, True)


def test_fd_prefix_needs_to_be_glued():
    # `echo 2 > x` prints "2"; `echo 2> x` redirects stderr.
    c = _cmd("echo 2 > x")
    assert c["args"] == ["2"] and c["stdout_file"] == "x"
    c = _cmd("echo 2> x")
    assert c["args"] == [] and c["stderr_file"] == "x"


def test_one_prefix_is_plain_stdout():
    c = _cmd("echo 1> x")
    assert c["args"] == [] and c["stdout_file"] == "x"


def test_redirect_without_target_raises():
    with pytest.raises(ParseError):
        _parse("echo >")
    with pytest.raises(ParseError):
        _parse("echo 2>")


def test_redirect_target_may_be_quoted():
    assert _cmd("echo > 'my file'")["stdout_file"] == "my file"


def test_redirect_glued_to_word():
    c = _cmd("echo hi>out")
    assert c["args"] == ["hi"] and c["stdout_file"] == "out"


def test_redirects_anywhere_in_the_command():
    c = _cmd("> out echo a < in b")
    assert c["name"] == "echo" and c["args"] == ["a", "b"]
    assert (c["stdin_file"], c["stdout_file"]) == ("in", "out")
