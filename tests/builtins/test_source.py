def test_source_runs_file_and_returns_last_status(tmp_path, full_shell, run):
    script = tmp_path / "s.ax"
    script.write_text("set SRC_X 1\nalias srcalias='echo from-file'\necho sourced\n")
    code, out, _ = run(full_shell, f"source {script}")
    assert (code, out) == (0, "sourced\n")
    assert full_shell.context.variables["SRC_X"] == "1"
    assert run(full_shell, "srcalias")[1] == "from-file\n"


def test_dot_alias_and_continuation(tmp_path, full_shell, run):
    script = tmp_path / "s.ax"
    script.write_text("echo a \\\n b\n")
    assert run(full_shell, f". {script}") == (0, "a b\n", "")


def test_source_missing_file_and_no_args(full_shell, run):
    code, _, err = run(full_shell, "source /nonexistent/file")
    assert code == 1 and "No such file" in err
    assert run(full_shell, "source")[0] == 2


def test_source_last_status_reflects_last_line(tmp_path, full_shell, run):
    script = tmp_path / "s.ax"
    script.write_text("true\nfalse\n")
    assert run(full_shell, f"source {script}")[0] == 1


def test_source_cannot_be_piped(full_shell, run):
    code, _, err = run(full_shell, "echo x | source /dev/null")
    assert code == 3 and "cannot be used in a pipeline" in err
