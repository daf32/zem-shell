"""read / printf."""

import io


def _read(full_shell, line, text):
    cmd = full_shell.commands["read"]
    return cmd.execute(line.split()[1:] if line != "read" else [], full_shell.context,
                       stdin=io.StringIO(text), stdout=io.StringIO(), stderr=io.StringIO())


def test_read_single_name(full_shell):
    assert _read(full_shell, "read X", "  hello world  \n") == 0
    assert full_shell.context.variables["X"] == "hello world"
    assert not full_shell.context.is_exported("X")


def test_read_splits_with_remainder(full_shell):
    _read(full_shell, "read A B", "one two three\n")
    assert full_shell.context.variables["A"] == "one"
    assert full_shell.context.variables["B"] == "two three"


def test_read_missing_fields_are_empty(full_shell):
    _read(full_shell, "read A B C", "one\n")
    assert [full_shell.context.variables[n] for n in "ABC"] == ["one", "", ""]


def test_read_default_reply_and_eof(full_shell):
    assert _read(full_shell, "read", "x\n") == 0
    assert full_shell.context.variables["REPLY"] == "x"
    assert _read(full_shell, "read Y", "") == 1


def test_read_backslash_handling(full_shell):
    _read(full_shell, "read X", "a\\ b\n")
    assert full_shell.context.variables["X"] == "a b"
    _read(full_shell, "read -r X", "a\\ b\n")
    assert full_shell.context.variables["X"] == "a\\ b"


def test_read_from_pipe_in_shell(full_shell, run):
    assert run(full_shell, "read X < /dev/null")[0] == 1
    assert run(full_shell, "echo hi | read X")[0] == 3  # main_thread_only in a pipeline


def test_read_bad_option_and_name(full_shell, run):
    assert run(full_shell, "read -q X")[0] == 2
    assert run(full_shell, "read 1x")[0] == 2
    assert run(full_shell, "read -p")[0] == 2


def test_printf_basic_and_reuse(full_shell, run):
    assert run(full_shell, "printf '%s-%s\\n' a b c d") == (0, "a-b\nc-d\n", "")
    assert run(full_shell, "printf 'x\\n'") == (0, "x\n", "")
    assert run(full_shell, "printf '%s\\n' a b") == (0, "a\nb\n", "")


def test_printf_numbers_width_precision(full_shell, run):
    assert run(full_shell, "printf '%5d|%-4s|%.2f|%x|%o|%c\\n' 42 ab 3.14159 255 8 hello")[1] \
        == "   42|ab  |3.14|ff|10|h\n"
    assert run(full_shell, "printf '%05d %+d %%\\n' 7 3")[1] == "00007 +3 %\n"


def test_printf_missing_args_and_bad_numbers(full_shell, run):
    assert run(full_shell, "printf '[%s][%d]\\n'")[1] == "[][0]\n"
    code, out, err = run(full_shell, "printf '%d\\n' abc")
    assert (code, out) == (1, "0\n") and "invalid number" in err


def test_printf_escapes_only_in_format(full_shell, run):
    assert run(full_shell, "printf '%s\\n' 'a\\tb'")[1] == "a\\tb\n"
    assert run(full_shell, "printf 'a\\tb\\101\\n'")[1] == "a\tbA\n"
    assert run(full_shell, "printf")[0] == 2
