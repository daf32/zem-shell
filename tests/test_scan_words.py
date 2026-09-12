"""`split_words` / `word_at`: quote-aware splitting with positions."""

import pytest

from zem.config.settings import AppConfig
from zem.core.scan import split_words, word_at


@pytest.fixture
def ops():
    return AppConfig().operators


def _values(text, ops):
    return [w.value for w in split_words(text, ops)]


def test_plain_words(ops):
    assert _values("git status -s", ops) == ["git", "status", "-s"]


def test_repeated_and_trailing_blanks(ops):
    assert _values("  git   status  ", ops) == ["git", "status"]


def test_double_quotes_keep_the_word_together(ops):
    assert _values('git commit -m "hello world"', ops) == [
        "git", "commit", "-m", "hello world",
    ]


def test_single_quotes_keep_the_word_together(ops):
    assert _values("echo 'a b' c", ops) == ["echo", "a b", "c"]


def test_quotes_nest_the_other_kind_literally(ops):
    assert _values("""echo "it's" 'say "hi"'""", ops) == ["echo", "it's", 'say "hi"']


def test_escaped_space_does_not_split(ops):
    assert _values(r"ls my\ file", ops) == ["ls", "my file"]


def test_command_substitution_is_one_word_and_is_not_executed(ops):
    # The whole `$( ... )` is opaque: spaces inside must not split it, and
    # nothing may run while the user is still typing.
    assert _values("echo $(ls -l) tail", ops) == ["echo", "$(ls -l)", "tail"]


def test_unclosed_quote_still_yields_a_word(ops):
    assert _values('echo "a b', ops) == ["echo", "a b"]


def test_raw_text_and_offsets(ops):
    words = split_words('git commit -m "a b"', ops)
    last = words[-1]
    assert last.text == '"a b"'
    assert last.value == "a b"
    assert (last.start, last.end) == (14, 19)
    assert all(w.text == 'git commit -m "a b"'[w.start:w.end] for w in words)


def test_redirects_are_flagged(ops):
    words = {w.value: w.is_redirect for w in split_words("cat a > out 2>> err", ops)}
    assert words[">"] and words["2>>"]
    assert not words["cat"] and not words["out"]


@pytest.mark.parametrize(
    "text, index, value",
    [
        ("git ch", 1, "ch"),          # cursor inside the second word
        ("git ", -1, None),           # cursor on a fresh word
        ("git", 0, "git"),            # cursor at the end of the first word
        ("", -1, None),               # empty line
        ("git commit -m 'a ", 3, "a "),  # inside an open quote
    ],
)
def test_word_at(ops, text, index, value):
    words, idx = word_at(text, ops)
    assert idx == index
    if value is not None:
        assert words[idx].value == value
