import os
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OperatorsConfig(BaseModel):
    variable: str = "$"
    pipe: str = "|"
    quote: str = "'"
    double_quote: str = "\""
    space: str = " "
    semicolon: str = ";"
    comment: str = "#"
    redirect_output: str = ">"
    redirect_append: str = ">>"
    redirect_input: str = "<"
    background: str = "&"
    and_if: str = "&&"
    or_if: str = "||"
    variable_start: str = "{"
    variable_end: str = "}"
    escape: str = "\\"

class InputSettings(BaseModel):
    prompt: str = "#"
    rprompt: bool = True
    show_full_path: bool = False
    path_depth: int = Field(default=1, ge=0)
    show_git_info: bool = True
    show_venv_info: bool = True
    show_exit_code: bool = True
    color_prompt: bool = True

class HistorySettings(BaseModel):
    enable: bool = True
    file: str = Field(default_factory=lambda: os.path.expanduser("~/.axonix_history"))
    max_entries: int = Field(default=1000, ge=1)
    load_on_start: bool = True
    save_on_exit: bool = True
    rotate: bool = True  # truncate to max_entries on save

class RCSettings(BaseModel):
    auto_create: bool = True
    file: str = Field(default_factory=lambda: os.path.expanduser("~/.axonixrc"))

class ColorScheme(BaseModel):
    """Color scheme for syntax highlighting and interface elements."""
    command: str = "#ffb86c"  # Orange
    variable: str = "#f1fa8c"  # Yellow
    operator: str = "#50fa7b"  # Green
    comment: str = "#6272a4"   # Gray-Blue
    string: str = "#ff79c6"    # Pink/Magenta
    path: str = "#8be9fd"      # Cyan
    prompt_symbol: str = "#ffffff"  # White
    exit_code_ok: str = "#50fa7b"   # Green
    exit_code_err: str = "#ff5555"  # Red
    error: str = "#ff5555"     # Red
    warning: str = "#ffb86c"   # Orange
    info: str = "#8be9fd"      # Cyan
    
    # Logo gradient colors
    logo_primary: str = "#8be9fd"      # Cyan
    logo_secondary: str = "#bd93f9"    # Purple
    logo_tertiary: str = "#6272a4"     # Blue-Gray

class VenvScheme(BaseModel):
    auto: bool = True

def _legacy_config_path() -> str:
    """Path to the historical config.json that lived in the project root."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json"))


def get_config_path() -> str:
    """Resolve the user-level config file path.

    Order of preference:
    1. ``AXONIX_CONFIG_PATH`` environment variable (explicit override)
    2. ``$XDG_CONFIG_HOME/axonix/config.json`` (defaults to
       ``~/.config/axonix/config.json``)
    """
    env_path = os.getenv("AXONIX_CONFIG_PATH")
    if env_path:
        return os.path.abspath(os.path.expanduser(env_path))

    xdg_home = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.abspath(os.path.join(xdg_home, "axonix", "config.json"))


CONFIG_PATH = get_config_path()

class AppConfig(BaseSettings):
    operators: OperatorsConfig = Field(default_factory=OperatorsConfig)
    input: InputSettings = Field(default_factory=InputSettings)
    history: HistorySettings = Field(default_factory=HistorySettings)
    rc: RCSettings = Field(default_factory=RCSettings)
    colors: ColorScheme = Field(default_factory=ColorScheme)
    active_theme: str = "default"
    venv: VenvScheme = Field(default_factory=VenvScheme)
    plugins: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("operators")
    @classmethod
    def validate_unique_operators(cls, v: OperatorsConfig) -> OperatorsConfig:
        """Ensure operator symbols are unique to avoid parsing conflicts."""
        items = v.model_dump()
        seen = {}
        for name, val in items.items():
            if val in seen:
                raise ValueError(
                    f"Operator '{name}' conflicts with '{seen[val]}' (same symbol '{val}')"
                )
            seen[val] = name
        return v

    model_config = SettingsConfigDict(
        json_file=CONFIG_PATH,
        json_file_encoding='utf-8',
        extra='ignore'
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings
    ):
        from pydantic_settings import JsonConfigSettingsSource
        # Resolve the path per instance: `AXONIX_CONFIG_PATH` may change
        # after import (tests point it at a temp file), and the class-level
        # `json_file` default is frozen at definition time.
        return (
            init_settings,
            JsonConfigSettingsSource(settings_cls, json_file=get_config_path()),
            env_settings,
        )

def _ensure_config_file(path: str) -> None:
    """Make sure ``path`` exists, migrating from the legacy project-root
    location when possible, otherwise creating a default config.

    Side-effect on import is intentional: it ensures
    ``JsonConfigSettingsSource`` has something to read on first run. We
    deliberately do NOT instantiate a module-level ``config = AppConfig()``
    afterwards — any module that wants the live config should construct
    ``AppConfig()`` itself (cheap, just re-reads the JSON), so a malformed
    config raises ``ValidationError`` from inside ``main()`` where it is
    properly handled, rather than at import time.
    """
    if os.path.exists(path):
        return

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        return

    legacy = _legacy_config_path()
    if legacy != path and os.path.isfile(legacy):
        try:
            import shutil
            shutil.move(legacy, path)
            return
        except OSError:
            pass

    import json
    # Build the defaults *before* touching ``path``: ``AppConfig()`` reads
    # ``CONFIG_PATH`` through ``JsonConfigSettingsSource``, and opening the
    # file for writing first would leave an empty file for it to choke on.
    defaults = AppConfig().model_dump()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4)
    except OSError:
        pass


_ensure_config_file(CONFIG_PATH)
