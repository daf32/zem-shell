"""Theme manager for Zem Shell."""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ThemeError(Exception):
    """A theme could not be imported, installed or exported; the message
    says why, in words meant for the user."""


#: What a theme may be called: it becomes a file name under `~/.zem/themes`,
#: so nothing that could name another directory.
THEME_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: A theme is a few dozen colours; anything bigger is not one.
MAX_THEME_BYTES = 256 * 1024


def theme_name(raw: object) -> str:
    """Normalise a theme name, or raise :class:`ThemeError`."""
    name = str(raw).strip().lower().replace(" ", "_")
    if not THEME_NAME.match(name):
        raise ThemeError(
            f"{str(raw)!r} is not a valid theme name "
            "(letters, digits, '_' and '-', up to 64 characters)"
        )
    return name


class ThemeManager:
    """Manages shell themes with validation."""
    
    # Required color keys that every theme must have
    REQUIRED_COLORS = {
        "command", "variable", "operator", "comment", "string", 
        "path", "prompt_symbol", "exit_code_ok", "exit_code_err", "error"
    }
    
    # Optional color keys
    OPTIONAL_COLORS = {
        "warning", "info", "logo_primary", "logo_secondary", "logo_tertiary"
    }
    
    # Regex pattern for valid hex colors
    HEX_COLOR_PATTERN = re.compile(r'^#[0-9A-Fa-f]{6}$')
    
    def __init__(self, config, extra_dirs=()):
        self.config = config
        #: Themes ship with the `theme` plugin, which passes its directory
        #: in through `extra_dirs`; the shell itself carries none.
        self._user_themes_dir = Path.home() / ".zem" / "themes"
        #: Directories contributed by plugins, between bundled and user.
        self._extra_dirs = [Path(p).expanduser() for p in extra_dirs]
        self._cached_themes: Optional[Dict] = None
        self._validation_errors: Dict[str, List[str]] = {}
    
    def get_themes_dirs(self) -> List[Path]:
        """Get all theme directories, weakest first."""
        dirs = [path for path in self._extra_dirs if path.exists()]
        if self._user_themes_dir.exists():
            dirs.append(self._user_themes_dir)
        return dirs
    
    def validate_color(self, color: str) -> bool:
        """Validate that a color is a valid hex color code."""
        if not isinstance(color, str):
            return False
        return bool(self.HEX_COLOR_PATTERN.match(color))
    
    def validate_theme(
        self, theme_data: dict, theme_name: str = "unknown"
    ) -> Tuple[bool, List[str]]:
        """Validate a theme's structure and colors.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check for required fields
        if "colors" not in theme_data:
            errors.append("Missing 'colors' section")
            return False, errors
        
        colors = theme_data["colors"]
        
        # Check for required color keys
        missing_required = self.REQUIRED_COLORS - set(colors.keys())
        if missing_required:
            errors.append(f"Missing required colors: {', '.join(sorted(missing_required))}")
        
        # Validate color values
        for key, value in colors.items():
            if not self.validate_color(value):
                errors.append(f"Invalid color for '{key}': {value} (expected hex like #RRGGBB)")
        
        # Warn about unknown color keys (but don't fail)
        all_known = self.REQUIRED_COLORS | self.OPTIONAL_COLORS
        unknown = set(colors.keys()) - all_known
        if unknown:
            # This is just a warning, not an error
            pass
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def list_themes(self, include_invalid: bool = False) -> Dict[str, dict]:
        """List all available themes.
        
        Args:
            include_invalid: If True, include themes that failed validation
        """
        if self._cached_themes is not None and not include_invalid:
            return self._cached_themes
        
        themes = {}
        self._validation_errors.clear()
        
        for themes_dir in self.get_themes_dirs():
            if not themes_dir.exists():
                continue
            for theme_file in themes_dir.glob("*.json"):
                try:
                    with open(theme_file, "r", encoding="utf-8") as f:
                        theme_data = json.load(f)
                        theme_name = theme_file.stem.lower()
                        
                        # Validate theme
                        is_valid, errors = self.validate_theme(theme_data, theme_name)
                        
                        if errors:
                            self._validation_errors[theme_name] = errors
                        
                        if is_valid or include_invalid:
                            themes[theme_name] = {
                                "path": str(theme_file),
                                "data": theme_data,
                                "valid": is_valid,
                                "errors": errors
                            }
                except json.JSONDecodeError as e:
                    self._validation_errors[theme_file.stem.lower()] = [f"Invalid JSON: {e}"]
                except OSError as e:
                    self._validation_errors[theme_file.stem.lower()] = [f"Read error: {e}"]
        
        if not include_invalid:
            self._cached_themes = themes
        return themes
    
    def get_validation_errors(self) -> Dict[str, List[str]]:
        """Get validation errors from last list_themes call."""
        return self._validation_errors.copy()
    
    def get_theme(self, name: str) -> Optional[dict]:
        """Get theme data by name."""
        themes = self.list_themes()
        theme = themes.get(name.lower())
        if theme:
            return theme["data"]
        return None
    
    def apply_theme(self, name: str, shell) -> bool:
        """Apply theme to shell (updates config and reloads style)."""
        theme = self.get_theme(name)
        if not theme:
            return False
        
        colors = theme.get("colors", {})
        
        for key, value in colors.items():
            if hasattr(shell.config.colors, key):
                setattr(shell.config.colors, key, value)

        shell.config.active_theme = name
        self._rebuild_style(shell)

        self._save_theme_to_config(name)
        
        return True
    
    def _rebuild_style(self, shell):
        """Rebuild prompt_toolkit style from current colors."""
        # Use shell's _build_style method to ensure consistency
        new_style = shell._build_style()
        shell.style = new_style
        
        # Update session style - this is critical for immediate effect
        if hasattr(shell, 'session') and shell.session is not None:
            shell.session.style = new_style
            # Force the application to refresh if it's running
            app = shell.session.app
            if app is not None and app.is_running:
                app.invalidate()
    
    def _save_theme_to_config(self, theme_name: str):
        """Persist the active theme name and its colours to the config file."""
        from zem.config.settings import get_config_path
        from zem.config.store import update_raw

        theme = self.get_theme(theme_name)

        def mutate(data: dict) -> None:
            data["active_theme"] = theme_name
            if theme:
                data["colors"] = theme.get("colors", {})

        try:
            update_raw(get_config_path(), mutate)
        except Exception:
            pass
    
    def preview_theme(self, name: str) -> Optional[str]:
        """Generate a preview of the theme."""
        theme = self.get_theme(name)
        if not theme:
            return None
        
        data = theme
        colors = data.get("colors", {})
        
        preview_lines = [
            f"Theme: {data.get('name', name)}",
            f"Author: {data.get('author', 'Unknown')}",
            f"Type: {data.get('type', 'dark')}",
            "",
            "Colors:",
        ]
        
        for key, value in colors.items():
            preview_lines.append(f"  {key}: {value}")
        
        return "\n".join(preview_lines)
    
    def export_theme(self, name: str, path: str) -> None:
        """Write the current colours as a theme file; raises :class:`ThemeError`."""
        theme_data = {
            "name": theme_name(name),
            "author": "User",
            "type": "custom",
            "colors": self.config.colors.model_dump()
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=4)
        except OSError as exc:
            raise ThemeError(f"cannot write {path}: {exc.strerror}") from exc

    def import_theme(self, path: str) -> str:
        """Copy a theme file into the user themes directory.

        Returns the name it was stored under. Raises :class:`ThemeError`
        for a file that cannot be read, is not a valid theme, or names
        itself something that is not a plain name.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                theme_data = json.load(f)
        except OSError as exc:
            raise ThemeError(f"cannot read {path}: {exc.strerror}") from exc
        except ValueError as exc:
            raise ThemeError(f"{path}: not valid JSON ({exc})") from exc
        return self._store(theme_data, fallback_name=Path(path).stem)

    HTTP_TIMEOUT = 10  # seconds; theme install blocks the shell

    def install_theme(self, url: str) -> str:
        """Download a theme and store it like :meth:`import_theme`.

        Only https (or http to this machine) is accepted: the file lands
        in the user's home directory under a name it chooses itself.
        """
        import urllib.error
        import urllib.request
        from urllib.parse import urlsplit

        from zem.utils.net import UnsafeURL, check_url

        try:
            check_url(url)
        except UnsafeURL as exc:
            raise ThemeError(str(exc)) from None
        try:
            with urllib.request.urlopen(url, timeout=self.HTTP_TIMEOUT) as response:  # noqa: S310
                raw = response.read(MAX_THEME_BYTES + 1)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ThemeError(f"cannot download {url}: {exc}") from exc
        if len(raw) > MAX_THEME_BYTES:
            raise ThemeError(f"{url}: larger than {MAX_THEME_BYTES // 1024} KiB, not a theme")
        try:
            theme_data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ThemeError(f"{url}: not valid JSON ({exc})") from exc
        return self._store(theme_data, fallback_name=Path(urlsplit(url).path).stem or "theme")

    def _store(self, theme_data: object, fallback_name: str) -> str:
        """Validate ``theme_data`` and write it under its (checked) name."""
        if not isinstance(theme_data, dict):
            raise ThemeError("a theme is a JSON object with a 'colors' section")
        name = theme_name(theme_data.get("name") or fallback_name)
        is_valid, errors = self.validate_theme(theme_data, name)
        if not is_valid:
            raise ThemeError("invalid theme: " + "; ".join(errors))

        self._user_themes_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self._user_themes_dir / f"{name}.json"
        # `theme_name` already forbids separators; this is the belt to
        # that pair of braces.
        if dest_path.resolve().parent != self._user_themes_dir.resolve():
            raise ThemeError(f"{name!r} would be written outside the themes directory")
        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=4)
        except OSError as exc:
            raise ThemeError(f"cannot write {dest_path}: {exc.strerror}") from exc

        self._cached_themes = None
        return name

    def get_theme_variants(self, base_name: str) -> List[str]:
        """Get all variants of a theme (e.g., dracula, dracula_light)."""
        themes = self.list_themes()
        base_lower = base_name.lower()
        
        # Remove _dark or _light suffix to get true base name
        true_base = base_lower.replace("_dark", "").replace("_light", "")
        
        variants = []
        for name in themes.keys():
            # Match base name or any variant (base_dark, base_light)
            name_base = name.replace("_dark", "").replace("_light", "")
            if name_base == true_base or name == true_base:
                variants.append(name)
        
        return sorted(variants)
