"""The spec registry client, and the `hints` builtin that drives it."""

import hashlib
import json

import pytest

from zem.hints import registry_client
from zem.hints.registry_client import RegistryError, fetch_index, fetch_spec, install

SPEC = {"schema_version": 1, "command": "demo", "description": "A demo tool",
        "subcommands": [{"name": "go"}]}
SPEC_BYTES = json.dumps(SPEC).encode()
SPEC_SHA = hashlib.sha256(SPEC_BYTES).hexdigest()
INDEX = {"schema_version": 1, "hints": [
    {"name": "demo", "command": "demo", "description": "A demo tool",
     "subcommands": 1, "size": len(SPEC_BYTES), "sha256": SPEC_SHA},
]}

BASE = "https://example.test/registry"


@pytest.fixture
def http(monkeypatch):
    """Serve a fake registry; record every URL requested."""
    requested = []

    def _install(responses):
        def _get(url):
            requested.append(url)
            if url not in responses:
                raise RegistryError(f"{url}: not found in the registry")
            payload = responses[url]
            if isinstance(payload, Exception):
                raise payload
            return payload

        monkeypatch.setattr(registry_client, "_get", _get)
        return requested

    _install.requested = requested
    return _install


def _default(http):
    return http({
        f"{BASE}/index.json": json.dumps(INDEX).encode(),
        f"{BASE}/hints/demo.json": SPEC_BYTES,
    })


def _cache(tmp_path):
    from zem.hints.registry_client import cache_path_for

    return cache_path_for(str(tmp_path / "hints"))


def test_fetch_index(http, tmp_path):
    _default(http)
    assert [e["name"] for e in fetch_index(BASE, _cache(tmp_path))] == ["demo"]


def test_index_is_cached(http, tmp_path):
    requested = _default(http)
    fetch_index(BASE, _cache(tmp_path))
    fetch_index(BASE, _cache(tmp_path))
    assert len(requested) == 1


def test_refresh_bypasses_the_cache(http, tmp_path):
    requested = _default(http)
    fetch_index(BASE, _cache(tmp_path))
    fetch_index(BASE, _cache(tmp_path), refresh=True)
    assert len(requested) == 2


def test_cache_is_per_registry(http, tmp_path):
    requested = http({
        f"{BASE}/index.json": json.dumps(INDEX).encode(),
        "https://other.test/index.json": json.dumps(INDEX).encode(),
    })
    fetch_index(BASE, _cache(tmp_path))
    fetch_index("https://other.test", _cache(tmp_path))
    assert len(requested) == 2


def test_malformed_index(http, tmp_path):
    http({f"{BASE}/index.json": b"{}"})
    with pytest.raises(RegistryError, match="not a valid registry index"):
        fetch_index(BASE, _cache(tmp_path))


def test_fetch_spec_checks_the_checksum(http):
    _default(http)
    with pytest.raises(RegistryError, match="checksum mismatch"):
        fetch_spec(BASE, "demo", "0" * 64)


def test_fetch_spec_rejects_a_broken_download(http):
    http({f"{BASE}/hints/demo.json": b"{not json"})
    with pytest.raises(RegistryError, match="not valid JSON"):
        fetch_spec(BASE, "demo")


def test_fetch_spec_rejects_an_invalid_spec(http):
    http({f"{BASE}/hints/demo.json": json.dumps({"schema_version": 1, "oops": 1}).encode()})
    with pytest.raises(RegistryError, match="invalid spec"):
        fetch_spec(BASE, "demo")


def test_install_writes_the_file(http, tmp_path):
    _default(http)
    path = install(BASE, "demo", tmp_path / "hints", SPEC_SHA)
    assert json.loads(path.read_text())["command"] == "demo"
    assert not list(path.parent.glob("*.tmp"))


def test_non_http_url_is_refused():
    with pytest.raises(RegistryError, match="non-HTTP"):
        registry_client._get("file:///etc/passwd")


# -- the builtin -----------------------------------------------------------

@pytest.fixture
def shell(full_shell, tmp_path, http):
    full_shell.config.hints.registry_url = BASE
    full_shell.config.hints.user_dir = str(tmp_path / "hints")
    _default(http)
    return full_shell


def test_search_lists_the_registry(shell, run):
    code, out, _ = run(shell, "hints search demo")
    assert code == 0 and "A demo tool" in out


def test_search_without_a_match(shell, run):
    code, out, _ = run(shell, "hints search nothinglikethis")
    assert code == 0 and "No spec matches" in out


def test_install_then_the_spec_is_used(shell, run):
    code, out, _ = run(shell, "hints install demo")
    assert code == 0, out
    assert "may run commands" in out  # the trust warning
    code, out, _ = run(shell, "hints list")
    assert "demo" in out and "user" in out


def test_install_an_unknown_spec(shell, run):
    code, _, err = run(shell, "hints install nope")
    assert code == 1 and "not in the registry" in err


def test_remove(shell, run):
    run(shell, "hints install demo")
    code, out, _ = run(shell, "hints remove demo")
    assert code == 0 and "Removed" in out
    code, _, err = run(shell, "hints remove demo")
    assert code == 1 and "not installed" in err


def test_update_reports_current_specs(shell, run):
    run(shell, "hints install demo")
    code, out, _ = run(shell, "hints update")
    assert code == 0 and "0 updated" in out


def test_update_replaces_a_changed_spec(shell, run, tmp_path):
    run(shell, "hints install demo")
    (tmp_path / "hints" / "demo.json").write_text('{"schema_version": 1, "command": "demo"}')
    code, out, _ = run(shell, "hints update")
    assert code == 0 and "demo: updated" in out


def test_network_failure_is_reported_not_raised(full_shell, tmp_path, monkeypatch, run):
    full_shell.config.hints.registry_url = BASE
    full_shell.config.hints.user_dir = str(tmp_path / "hints")

    def _boom(url):
        raise RegistryError(f"{url}: Name or service not known")

    monkeypatch.setattr(registry_client, "_get", _boom)
    code, _, err = run(full_shell, "hints search demo")
    assert code == 1 and "hints:" in err


def test_show_and_validate(full_shell, run, tmp_path):
    code, out, _ = run(full_shell, "hints show git")
    assert code == 0 and "checkout" in out

    good = tmp_path / "ok.json"
    good.write_text(json.dumps(SPEC))
    code, out, _ = run(full_shell, f"hints validate {good}")
    assert code == 0 and "ok (demo" in out

    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": 1, "command": "x", "nope": 1}')
    code, _, err = run(full_shell, f"hints validate {bad}")
    assert code == 1 and "nope" in err


def test_unknown_subcommand(full_shell, run):
    code, _, err = run(full_shell, "hints frobnicate")
    assert code == 2 and "unknown subcommand" in err


def test_the_index_cache_is_not_mistaken_for_a_spec(shell, run, tmp_path):
    """The cache used to live beside the specs, where the loader read it as
    a spec and reported it as broken."""
    run(shell, "hints search demo")
    code, out, err = run(shell, "hints list")
    assert code == 0
    assert "failed to load" not in out and "index" not in err


def test_update_ignores_anything_that_is_not_a_spec(shell, run, tmp_path):
    run(shell, "hints install demo")
    (tmp_path / "hints" / ".hidden.json").write_text("{}")
    code, out, _ = run(shell, "hints update")
    assert code == 0 and "hidden" not in out


def test_the_cache_lives_outside_the_spec_directory(shell, run, tmp_path):
    from zem.hints.registry_client import cache_path_for

    run(shell, "hints search demo")
    cache = cache_path_for(shell.config.hints.user_dir)
    assert cache.exists()
    assert cache.parent != (tmp_path / "hints")
