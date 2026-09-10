"""type / command / true / false / :"""


def test_true_false_colon(full_shell, run):
    assert run(full_shell, "true") == (0, "", "")
    assert run(full_shell, "false")[0] == 1
    assert run(full_shell, ":") == (0, "", "")
    assert run(full_shell, "false || echo fallback") == (0, "fallback\n", "")


def test_type_builtin_alias_file_and_missing(full_shell, run):
    assert run(full_shell, "type cd") == (0, "cd is a shell builtin\n", "")
    run(full_shell, "alias ll='ls -la'")
    assert run(full_shell, "type ll") == (0, "ll is an alias for ls -la\n", "")
    code, out, _ = run(full_shell, "type ls")
    assert code == 0 and out.startswith("ls is /") and out.endswith("/ls\n")
    code, out, err = run(full_shell, "type nope-cmd-xyz")
    assert (code, out) == (1, "") and "not found" in err


def test_type_t_and_multiple(full_shell, run):
    run(full_shell, "alias ll='ls'")
    assert run(full_shell, "type -t cd ll ls")[1] == "builtin\nalias\nfile\n"
    assert run(full_shell, "type -x cd")[0] == 2
    assert run(full_shell, "type")[0] == 2


def test_command_v_and_V(full_shell, run):
    code, out, _ = run(full_shell, "command -v cd ls")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "cd" and lines[1].endswith("/ls")
    assert run(full_shell, "command -v nope-cmd-xyz") == (1, "", "")
    assert run(full_shell, "command -V cd")[1] == "cd is a shell builtin\n"
    assert run(full_shell, "command -v")[0] == 2


def test_command_bypasses_builtin_and_alias(full_shell, run):
    # `echo` is a builtin; `command echo` must run /bin/echo. Both print
    # the same text, so check the *builtin-only* flag -E handling differs:
    # builtin echo -E prints "a\tb" verbatim, and so does /bin/echo, so use
    # a builtin that has no external counterpart instead.
    code, _, err = run(full_shell, "command get X")
    assert code == 2 and "Unknown command" in err  # no /usr/bin/get
    run(full_shell, "alias echo='echo aliased'")
    assert run(full_shell, "echo x")[1] == "aliased x\n"
    assert run(full_shell, "command echo x")[1] == "x\n"


def test_command_in_pipeline(full_shell, run):
    assert run(full_shell, "command echo piped | cat")[1] == "piped\n"
