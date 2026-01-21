"""Weather plugin using Open-Meteo API."""
import json
import urllib.request
import urllib.parse
from axonix.builtins.base import BaseCommand
from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import Completion
from typing import TYPE_CHECKING, Iterable, List

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext
    from prompt_toolkit.document import Document

class WeatherCompleter(BaseArgCompleter):
    """Suggests cities from a predefined list or history."""
    
    CITIES = [
        "London", "New York", "Tokyo", "Paris", "Berlin", "Moscow", 
        "Dubai", "Singapore", "Barcelona", "Madrid", "Rome", 
        "Toronto", "Sydney", "Mumbai", "Beijing", "San Francisco"
    ]

    def get_completions(self, document: "Document", parts: List[str], word_before: str) -> Iterable[Completion]:
        # weather [CITY]
        if len(parts) >= 1:
            for city in self.CITIES:
                if city.lower().startswith(word_before.lower()):
                    yield Completion(city, start_position=-len(word_before))

class WeatherCommand(BaseCommand):
    name = "weather"
    help = "Show weather forecast"
    usage = "weather [city]"
    tags = ["plugin", "web"]
    
    API_URL = "https://api.open-meteo.com/v1/forecast"
    GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"

    def get_completer(self):
        return WeatherCompleter()

    def get_default_config(self) -> dict:
        return {
            "default_city": "Moscow"
        }

    def execute(self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None):
        # 1. Get city name (arg > config > default)
        city = " ".join(args)
        if not city:
            config = self.get_plugin_config(context)
            city = config.get("default_city", "London")
        
        self._write(f"🌍 Fetching weather for: {city}...\n", stdout)
        
        try:
            # 2. Geocoding
            lat, lon, display_name = self._get_coordinates(city)
            
            # 3. Weather Data
            weather = self._get_weather(lat, lon)
            
            # 4. Display
            temp = weather["current_weather"]["temperature"]
            wind = weather["current_weather"]["windspeed"]
            code = weather["current_weather"]["weathercode"]
            
            icon = self._get_weather_icon(code)
            
            from prompt_toolkit import print_formatted_text
            from prompt_toolkit.formatted_text import FormattedText
            
            # Use shell colors
            c = getattr(context._shell.config.colors, "info", "#ffffff")
            val_c = getattr(context._shell.config.colors, "variable", "#ffffff")
            
            print_formatted_text(FormattedText([
                ("", "\n"),
                (c, f"{icon}  Weather in {display_name}:\n"),
                ("", "   Temperature: "), (val_c, f"{temp}°C\n"),
                ("", "   Wind Speed:  "), (val_c, f"{wind} km/h\n"),
                ("", "\n")
            ]))
            
        except Exception as e:
            self._write(f"❌ Error: {e}\n", stdout)

    def _get_coordinates(self, city: str):
        params = urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
        url = f"{self.GEO_URL}?{params}"
        
        with urllib.request.urlopen(url) as response:
            data = json.load(response)
            
        if not data.get("results"):
            raise ValueError(f"City '{city}' not found.")
            
        result = data["results"][0]
        return result["latitude"], result["longitude"], f"{result['name']}, {result.get('country', '')}"

    def _get_weather(self, lat, lon):
        params = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "current_weather": "true"})
        url = f"{self.API_URL}?{params}"
        
        with urllib.request.urlopen(url) as response:
            return json.load(response)

    def _get_weather_icon(self, code):
        # WMO Weather interpretation codes (WW)
        if code == 0: return "☀️"
        if code in [1, 2, 3]: return "⛅"
        if code in [45, 48]: return "🌫"
        if code in [51, 53, 55]: return "zz☔"
        if code in [61, 63, 65]: return "☔"
        if code in [80, 81, 82]: return "🌧"
        if code in [95, 96, 99]: return "⛈"
        if code in [71, 73, 75]: return "❄️"
        return "❓"
