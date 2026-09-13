"""A weather report, and the smallest complete example of a plugin.

Everything a plugin is expected to do is here and nowhere else: a command
with an exit code, errors on stderr, defaults that land in `config.json`
on first run, colours taken from the active theme, and a `Plugin` class
so `plugin list` and `plugin disable weather` can see it. Copy this file
into `~/.zem/plugins/` and edit it -- that is a working plugin.

The data comes from Open-Meteo, which needs no API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Optional, Tuple

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError
from zem.plugin import Plugin

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO weather codes, grouped the way a one-glance report wants them.
ICONS = (
    ((0,), "☀️"),
    ((1, 2, 3), "⛅"),
    ((45, 48), "🌫"),
    ((51, 53, 55, 56, 57), "🌦"),
    ((61, 63, 65, 66, 67), "☔"),
    ((71, 73, 75, 77, 85, 86), "❄️"),
    ((80, 81, 82), "🌧"),
    ((95, 96, 99), "⛈"),
)


class WeatherError(Exception):
    """Something the user should be told about, in words they can act on."""


class WeatherCommand(BaseCommand):
    name = "weather"
    help = "Show the current weather"
    usage = "weather [CITY]"
    tags = ["plugin", "web"]
    examples = [
        "weather           - The city from the config",
        "weather Berlin    - Somewhere else",
    ]

    def get_default_config(self) -> dict:
        """Written into `config.json` under `plugins.weather` on first run."""
        return {"default_city": "Moscow", "timeout_s": 5}

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        if args and args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")

        settings = self.get_plugin_config(context)
        city = " ".join(args) or str(settings.get("default_city") or "London")
        timeout = settings.get("timeout_s")
        timeout = float(timeout) if isinstance(timeout, (int, float)) else 5.0

        try:
            place, latitude, longitude = self._locate(city, timeout)
            temperature, wind, code = self._forecast(latitude, longitude, timeout)
        except WeatherError as exc:
            # A failure goes to stderr and shows in `$?`, so `weather || ...`
            # works like it does for every other command.
            self._write_err(f"weather: {exc}\n", stderr)
            return 1

        colors = self._colors(context)
        self._print_colored([
            (colors["info"], f"{_icon(code)}  {place}"),
            ("", "  "),
            (colors["value"], f"{temperature:g}°C"),
            (colors["dim"], f"  wind {wind:g} km/h"),
        ], stdout)
        return 0

    # -- the network ---------------------------------------------------------

    def _locate(self, city: str, timeout: float) -> Tuple[str, float, float]:
        data = self._get(GEOCODING_URL, timeout, name=city, count=1, format="json")
        results = data.get("results") or []
        if not results:
            raise WeatherError(f"no place called {city!r}")
        first = results[0]
        country = first.get("country")
        return (
            f"{first['name']}, {country}" if country else first["name"],
            first["latitude"],
            first["longitude"],
        )

    def _forecast(self, latitude: float, longitude: float,
                  timeout: float) -> Tuple[float, float, int]:
        data = self._get(FORECAST_URL, timeout, latitude=latitude,
                         longitude=longitude, current_weather="true")
        current = data.get("current_weather") or {}
        try:
            return current["temperature"], current["windspeed"], current["weathercode"]
        except KeyError as exc:
            raise WeatherError(f"the forecast is missing {exc}") from exc

    @staticmethod
    def _get(url: str, timeout: float, **params) -> dict:
        """One request, with every failure named in terms of the service.

        `KeyboardInterrupt` is deliberately not caught: Ctrl-C during a
        slow request must end the command, not be reported as weather.
        """
        query = urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(f"{url}?{query}", timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise WeatherError(f"the weather service answered HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise WeatherError(f"cannot reach the weather service ({exc})") from exc
        except ValueError as exc:
            raise WeatherError("the weather service answered with nonsense") from exc
        if not isinstance(payload, dict):
            raise WeatherError("the weather service answered with nonsense")
        return payload

    # -- looks ----------------------------------------------------------------

    @staticmethod
    def _colors(context: "ExecutionContext") -> dict:
        """Theme colours, with fallbacks: a plugin may run without a shell."""
        shell = getattr(context, "_shell", None)
        scheme = getattr(getattr(shell, "config", None), "colors", None)
        return {
            "info": getattr(scheme, "info", "#8be9fd"),
            "value": getattr(scheme, "variable", "#f1fa8c"),
            "dim": getattr(scheme, "comment", "#6272a4"),
        }


def _icon(code: Optional[int]) -> str:
    for codes, icon in ICONS:
        if code in codes:
            return icon
    return "❓"


class WeatherPlugin(Plugin):
    name = "weather"
    version = "1.0.0"
    description = "The `weather` command (Open-Meteo)"

    def commands(self):
        return [WeatherCommand]
