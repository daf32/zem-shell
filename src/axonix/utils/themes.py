"""Theme manager for Axonix Shell."""
import os
import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class ThemeValidationError(Exception):
    """Raised when theme validation fails."""
    pass


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
    
    def __init__(self, config):
        self.config = config
        self._themes_dir = Path(__file__).parent.parent / "themes"
        self._user_themes_dir = Path.home() / ".axonix" / "themes"
        self._cached_themes: Optional[Dict] = None
        self._validation_errors: Dict[str, List[str]] = {}
    
    def get_themes_dirs(self) -> List[Path]:
        """Get all theme directories."""
        dirs = [self._themes_dir]
        if self._user_themes_dir.exists():
            dirs.append(self._user_themes_dir)
        return dirs
    
    def validate_color(self, color: str) -> bool:
        """Validate that a color is a valid hex color code."""
        if not isinstance(color, str):
            return False
        return bool(self.HEX_COLOR_PATTERN.match(color))
    
    def validate_theme(self, theme_data: dict, theme_name: str = "unknown") -> Tuple[bool, List[str]]:
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
        """Save active theme name to config file."""
        from axonix.config.settings import CONFIG_PATH
        
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            else:
                config_data = {}

            config_data["active_theme"] = theme_name

            theme = self.get_theme(theme_name)
            if theme:
                config_data["colors"] = theme.get("colors", {})

            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
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
    
    def export_theme(self, name: str, path: str) -> bool:
        """Export current colors as a theme file."""
        theme_data = {
            "name": name,
            "author": "User",
            "type": "custom",
            "colors": self.config.colors.model_dump()
        }
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=4)
            return True
        except Exception:
            return False
    
    def import_theme(self, path: str) -> Optional[str]:
        """Import a theme from file to user themes directory."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                theme_data = json.load(f)
            
            self._user_themes_dir.mkdir(parents=True, exist_ok=True)
            name = theme_data.get("name", Path(path).stem).lower().replace(" ", "_")
            
            dest_path = self._user_themes_dir / f"{name}.json"
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=4)

            self._cached_themes = None
            
            return name
        except Exception:
            return None
    
    HTTP_TIMEOUT = 10  # seconds; theme install blocks the shell

    def install_theme(self, url: str) -> Optional[str]:
        """Download and install a theme from URL."""
        import shutil
        import tempfile
        import urllib.request

        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json')
            os.close(tmp_fd)

            with urllib.request.urlopen(url, timeout=self.HTTP_TIMEOUT) as response, \
                    open(tmp_path, "wb") as out:
                shutil.copyfileobj(response, out)
            with open(tmp_path, "r", encoding="utf-8") as f:
                json.load(f)

            name = self.import_theme(tmp_path)
            os.unlink(tmp_path)

            return name
        except Exception:
            return None
    
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
    
    def has_light_variant(self, name: str) -> bool:
        """Check if theme has a light variant."""
        base = name.lower().replace("_dark", "").replace("_light", "")
        light_name = f"{base}_light"
        return light_name in self.list_themes()
    
    def has_dark_variant(self, name: str) -> bool:
        """Check if theme has a dark variant."""
        base = name.lower().replace("_dark", "").replace("_light", "")
        dark_name = f"{base}_dark"
        # Also check base name without suffix (often the dark version)
        return dark_name in self.list_themes() or base in self.list_themes()
