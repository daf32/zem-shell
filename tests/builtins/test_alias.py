"""alias / unalias."""


def test_alias_define_and_use(full_shell, run):
    assert run(full_shell, "alias hi='echo hello'")[0] == 0
    assert run(full_shell, "hi there") == (0, "hello there\n", "")


def test_alias_value_keeps_inner_quotes(full_shell, run):
    run(full_shell, """alias q='echo "a b"'""")
    assert full_shell.context.aliases["q"] == 'echo "a b"'
    assert run(full_shell, "q") == (0, "a b\n", "")


def test_alias_listing_is_resourceable(full_shell, run):
    run(full_shell, """alias w='echo "x y"'""")
    code, out, _ = run(full_shell, "alias")
    assert out == """alias w='echo "x y"'\n"""
    run(full_shell, "unalias w")
    run(full_shell, out.strip())
    assert run(full_shell, "w") == (0, "x y\n", "")


def test_alias_listing_escapes_single_quotes(full_shell, run):
    # Alias values are shell text and get re-parsed on use, so a lone
    # quote inside is a user error at *use* time; the listing must still
    # round-trip the stored text exactly.
    full_shell.context.aliases["w"] = "echo it's"
    assert run(full_shell, "alias w")[1] == "alias w='echo it'\\''s'\n"


def test_alias_show_one_and_missing(full_shell, run):
    run(full_shell, "alias a='echo 1'")
    assert run(full_shell, "alias a") == (0, "alias a='echo 1'\n", "")
    code, out, err = run(full_shell, "alias nope")
    assert (code, out) == (1, "")
    assert "not found" in err


def test_alias_p_flag_lists(full_shell, run):
    run(full_shell, "alias a='echo 1'")
    assert run(full_shell, "alias -p")[1] == "alias a='echo 1'\n"


def test_unalias_removes_and_reports_missing(full_shell, run):
    run(full_shell, "alias a='echo 1'")
    assert run(full_shell, "unalias a")[0] == 0
    assert "a" not in full_shell.context.aliases
    code, _, err = run(full_shell, "unalias a")
    assert code == 1 and "not found" in err


def test_unalias_all_and_usage(full_shell, run):
    run(full_shell, "alias a='echo 1'; alias b='echo 2'")
    assert run(full_shell, "unalias -a")[0] == 0
    assert full_shell.context.aliases == {}
    assert run(full_shell, "unalias")[0] == 2
