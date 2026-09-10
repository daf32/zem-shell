def test_echo_plain(full_shell, run):
    assert run(full_shell, "echo a b") == (0, "a b\n", "")


def test_echo_n(full_shell, run):
    assert run(full_shell, "echo -n a") == (0, "a", "")


def test_echo_e_and_E(full_shell, run):
    assert run(full_shell, r"echo -e 'a\tb'") == (0, "a\tb\n", "")
    assert run(full_shell, r"echo -E 'a\tb'") == (0, "a\\tb\n", "")
    assert run(full_shell, r"echo 'a\tb'") == (0, "a\\tb\n", "")


def test_echo_combined_flags_and_literal_dash(full_shell, run):
    assert run(full_shell, r"echo -ne 'x\n'") == (0, "x\n", "")
    assert run(full_shell, "echo -x y") == (0, "-x y\n", "")
    assert run(full_shell, "echo - y") == (0, "- y\n", "")
