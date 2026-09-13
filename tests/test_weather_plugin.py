"""The bundled example plugin: exit codes, stderr, config, no bare excepts."""

import json
import urllib.error
import urllib.request

import pytest

from zem.plugins.weather import WeatherCommand, WeatherPlugin, _icon

PLACE = {"results": [{"name": "Berlin", "country": "Germany",
                      "latitude": 52.5, "longitude": 13.4}]}
FORECAST = {"current_weather": {"temperature": 7.0, "windspeed": 11.0, "weathercode": 3}}


@pytest.fixture
def answers(monkeypatch):
    """Serve canned JSON, and record what was asked for."""
    served: dict = {"calls": [], "payloads": [PLACE, FORECAST]}

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, *a):
            return json.dumps(self._payload).encode()

    def fake_urlopen(url, timeout=None):
        served["calls"].append((url, timeout))
        payload = served["payloads"].pop(0)
        if isinstance(payload, Exception):
            raise payload
        return Response(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return served


def test_reports_the_weather(full_shell, run, answers):
    code, out, err = run(full_shell, "weather Berlin")
    assert code == 0 and err == ""
    assert "Berlin, Germany" in out and "7°C" in out and "11 km/h" in out
    assert "⛅" in out  # weathercode 3
    assert len(answers["calls"]) == 2


def test_uses_the_city_from_the_plugin_config(full_shell, run, answers):
    full_shell.config.plugins["weather"] = {"default_city": "Oslo", "timeout_s": 2}
    assert run(full_shell, "weather")[0] == 0
    url, timeout = answers["calls"][0]
    assert "name=Oslo" in url and timeout == 2


def test_default_config_is_what_lands_in_the_config_file():
    assert WeatherCommand().get_default_config() == {"default_city": "Moscow", "timeout_s": 5}


def test_an_unknown_city_fails_on_stderr(full_shell, run, answers):
    answers["payloads"] = [{"results": []}]
    code, out, err = run(full_shell, "weather Atlantis")
    assert code == 1
    assert "no place called 'Atlantis'" in err
    assert out == ""


@pytest.mark.parametrize("failure, expected", [
    (urllib.error.URLError("offline"), "cannot reach"),
    (urllib.error.HTTPError("u", 503, "busy", None, None), "HTTP 503"),
    (OSError("socket"), "cannot reach"),
])
def test_a_broken_service_is_reported_not_raised(full_shell, run, answers, failure, expected):
    answers["payloads"] = [failure]
    code, _, err = run(full_shell, "weather Berlin")
    assert code == 1 and expected in err


def test_a_missing_field_is_reported(full_shell, run, answers):
    answers["payloads"] = [PLACE, {"current_weather": {"temperature": 1}}]
    code, _, err = run(full_shell, "weather Berlin")
    assert code == 1 and "missing" in err


def test_ctrl_c_is_not_swallowed(full_shell, run, monkeypatch):
    def interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(urllib.request, "urlopen", interrupt)
    assert run(full_shell, "weather Berlin")[0] == 130


def test_an_unknown_option_is_a_usage_error(full_shell, run):
    assert run(full_shell, "weather --tomorrow")[0] == 2


def test_it_is_a_plugin_the_shell_can_list_and_disable(full_shell):
    record = next(r for r in full_shell.plugins.loaded if r.name == "weather")
    assert isinstance(record.plugin, WeatherPlugin)
    assert WeatherCommand in list(record.plugin.commands())


@pytest.mark.parametrize("code, icon", [(0, "☀️"), (3, "⛅"), (95, "⛈"), (None, "❓"), (7, "❓")])
def test_icons(code, icon):
    assert _icon(code) == icon
