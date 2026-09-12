"""Value sources: static, dynamic, cached, and failing safely."""

import subprocess

import pytest

from zem.config.settings import HintsSettings
from zem.hints import sources
from zem.hints.providers import PROVIDERS
from zem.hints.sources import SourceContext, Suggestion, resolve
from zem.hints.spec import parse_spec


def _source(payload, **spec_extra):
    spec = parse_spec({
        "schema_version": 1, "command": "demo",
        "args": [{"name": "x", "source": payload}], **spec_extra,
    })
    return spec.args[0].source


def _ctx(tmp_path, **kwargs):
    kwargs.setdefault("settings", HintsSettings())
    return SourceContext(cwd=str(tmp_path), **kwargs)


def test_values_source(tmp_path):
    src = _source({"type": "values", "items": ["a", {"value": "b", "description": "Bee"}]})
    assert resolve(src, _ctx(tmp_path)) == [Suggestion("a", ""), Suggestion("b", "Bee")]


def test_path_sources_are_not_resolved_here(tmp_path):
    # files/dirs/none are served by the path completer, not by this module.
    for payload in ({"type": "files"}, {"type": "dirs"}, {"type": "none"}):
        assert resolve(_source(payload), _ctx(tmp_path)) == []


def test_command_source_parses_columns(tmp_path, fake_run):
    fake_run(stdout="main\tinit\ndev\twip\n")
    src = _source({"type": "command", "run": ["git", "branch"],
                   "parse": {"separator": "\t"}})
    assert resolve(src, _ctx(tmp_path)) == [Suggestion("main", "init"), Suggestion("dev", "wip")]


def test_command_source_without_separator_takes_whole_lines(tmp_path, fake_run):
    fake_run(stdout="origin\nupstream\n\n")
    src = _source({"type": "command", "run": ["git", "remote"]})
    assert [s.value for s in resolve(src, _ctx(tmp_path))] == ["origin", "upstream"]


def test_command_result_is_cached(tmp_path, fake_run):
    calls = fake_run(stdout="main\n")
    src = _source({"type": "command", "run": ["git", "branch"], "cache_ttl_ms": 60_000})
    ctx = _ctx(tmp_path)
    resolve(src, ctx)
    resolve(src, ctx)
    assert len(calls) == 1


def test_cache_expires(tmp_path, fake_run, monkeypatch):
    calls = fake_run(stdout="main\n")
    src = _source({"type": "command", "run": ["git", "branch"], "cache_ttl_ms": 10})
    clock = [1000.0]
    monkeypatch.setattr(sources.time, "monotonic", lambda: clock[0])
    resolve(src, _ctx(tmp_path))
    clock[0] += 1.0
    resolve(src, _ctx(tmp_path))
    assert len(calls) == 2


def test_cache_key_includes_cwd(tmp_path, fake_run):
    calls = fake_run(stdout="main\n")
    src = _source({"type": "command", "run": ["git", "branch"], "cache_ttl_ms": 60_000})
    resolve(src, _ctx(tmp_path))
    other = tmp_path / "other"
    other.mkdir()
    resolve(src, _ctx(other))
    assert len(calls) == 2


def test_global_scope_ignores_cwd(tmp_path, fake_run):
    calls = fake_run(stdout="img\n")
    src = _source({"type": "command", "run": ["docker", "images"],
                   "cache_scope": "global", "cache_ttl_ms": 60_000})
    resolve(src, _ctx(tmp_path))
    other = tmp_path / "other"
    other.mkdir()
    resolve(src, _ctx(other))
    assert len(calls) == 1


@pytest.mark.parametrize("failure", [
    {"returncode": 1},
    {"exc": subprocess.TimeoutExpired(cmd="git", timeout=0.3)},
    {"exc": FileNotFoundError("no such binary")},
])
def test_failures_are_silent_and_empty(tmp_path, fake_run, failure):
    fake_run(stdout="ignored\n", **failure)
    src = _source({"type": "command", "run": ["git", "branch"]})
    assert resolve(src, _ctx(tmp_path)) == []


def test_missing_binary_is_negatively_cached(tmp_path, fake_run):
    calls = fake_run(exc=FileNotFoundError("nope"))
    src = _source({"type": "command", "run": ["brew", "list"], "cache_ttl_ms": 0})
    resolve(src, _ctx(tmp_path))
    resolve(src, _ctx(tmp_path))
    assert len(calls) == 1


def test_nonzero_is_kept_when_allowed(tmp_path, fake_run):
    fake_run(stdout="partial\n", returncode=2)
    src = _source({"type": "command", "run": ["x"], "accept_nonzero": True})
    assert [s.value for s in resolve(src, _ctx(tmp_path))] == ["partial"]


def test_guard_blocks_the_expensive_call(tmp_path, fake_run):
    calls = fake_run(returncode=128)  # not a git repository
    src = _source({"type": "command", "run": ["git", "for-each-ref"],
                   "guard": {"run": ["git", "rev-parse", "--is-inside-work-tree"]}})
    assert resolve(src, _ctx(tmp_path)) == []
    assert [c[0][0] for c in calls] == ["git"]  # only the guard ran
    assert len(calls) == 1


def test_subprocess_is_isolated_from_the_terminal(tmp_path, fake_run):
    calls = fake_run(stdout="main\n")
    resolve(_source({"type": "command", "run": ["git", "branch"]}), _ctx(tmp_path))
    kwargs = calls[0][1]
    # Without its own session the helper joins the shell's foreground
    # process group and can steal the terminal.
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert kwargs["cwd"] == str(tmp_path)


def test_max_items_truncates(tmp_path, fake_run):
    fake_run(stdout="\n".join(f"b{i}" for i in range(50)))
    src = _source({"type": "command", "run": ["git", "branch"], "parse": {"max_items": 5}})
    assert len(resolve(src, _ctx(tmp_path))) == 5


def test_skip_lines(tmp_path, fake_run):
    fake_run(stdout="HEADER\na\nb\n")
    src = _source({"type": "command", "run": ["x"], "parse": {"skip_lines": 1}})
    assert [s.value for s in resolve(src, _ctx(tmp_path))] == ["a", "b"]


def test_dynamic_switch_disables_shelling_out(tmp_path, fake_run):
    calls = fake_run(stdout="main\n")
    src = _source({"type": "command", "run": ["git", "branch"]})
    ctx = _ctx(tmp_path, settings=HintsSettings(dynamic=False))
    assert resolve(src, ctx) == []
    assert calls == []


def test_dynamic_switch_keeps_static_values(tmp_path):
    src = _source({"type": "values", "items": ["a"]})
    ctx = _ctx(tmp_path, settings=HintsSettings(dynamic=False))
    assert [s.value for s in resolve(src, ctx)] == ["a"]


def test_min_prefix_defers_expensive_sources(tmp_path, fake_run):
    calls = fake_run(stdout="pkg\n")
    src = _source({"type": "command", "run": ["brew", "search"], "min_prefix": 2})
    assert resolve(src, _ctx(tmp_path, prefix="a")) == []
    assert calls == []
    assert [s.value for s in resolve(src, _ctx(tmp_path, prefix="ab"))] == ["pkg"]


def test_provider_source(tmp_path):
    PROVIDERS.register("test.things", lambda ctx: ["one", ("two", "second")], override=True)
    src = _source({"type": "provider", "name": "test.things"})
    assert resolve(src, _ctx(tmp_path)) == [Suggestion("one", ""), Suggestion("two", "second")]


def test_provider_receives_its_spec_args(tmp_path):
    seen = {}

    def _capture(ctx):
        seen.update(ctx.args)
        return []

    PROVIDERS.register("test.args", _capture, override=True)
    src = _source({"type": "provider", "name": "test.args", "args": {"include_remotes": True}})
    resolve(src, _ctx(tmp_path))
    assert seen == {"include_remotes": True}


def test_unknown_provider_is_not_fatal(tmp_path):
    assert resolve(_source({"type": "provider", "name": "nope.gone"}), _ctx(tmp_path)) == []


def test_broken_provider_is_not_fatal(tmp_path):
    def _explode(ctx):
        raise RuntimeError("boom")

    PROVIDERS.register("test.broken", _explode, override=True)
    assert resolve(_source({"type": "provider", "name": "test.broken"}), _ctx(tmp_path)) == []


def test_registering_twice_needs_override():
    PROVIDERS.register("test.dup", lambda ctx: [], override=True)
    with pytest.raises(ValueError, match="already registered"):
        PROVIDERS.register("test.dup", lambda ctx: [])


def test_npm_scripts_reads_package_json(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"dev": "vite", "build": "vite build"}}')
    src = _source({"type": "provider", "name": "npm.scripts"})
    assert resolve(src, _ctx(tmp_path)) == [
        Suggestion("dev", "vite"), Suggestion("build", "vite build"),
    ]


def test_npm_scripts_without_package_json(tmp_path):
    assert resolve(_source({"type": "provider", "name": "npm.scripts"}), _ctx(tmp_path)) == []


def test_config_keys_see_live_values(tmp_path, full_shell):
    full_shell.config.input.path_depth = 7
    src = _source({"type": "provider", "name": "zem.config_keys"})
    found = dict(resolve(src, _ctx(tmp_path, shell=full_shell)))
    assert found["input.path_depth"] == "7"
