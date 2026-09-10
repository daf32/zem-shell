"""Utilities for working with colors and formatting."""
from typing import Optional

from axonix.config.settings import AppConfig


def get_colors(config: Optional[AppConfig] = None):
    """Get the current color scheme from config."""
    if config is None:
        config = AppConfig()
    return config.colors

def colorize(text: str, color: str) -> str:
    """Wrap text in HTML color tags for prompt_toolkit."""
    return f'<{color}>{text}</{color}>'

def bold(text: str) -> str:
    """Make text bold."""
    return f'<b>{text}</b>'

def error_tag(config: Optional[AppConfig] = None):
    """Get formatted error tag."""
    if config is None:
        config = AppConfig()
    # Convert hex to ansi color name
    return '<ansired><b>[error]</b></ansired>'

def warning_tag(config: Optional[AppConfig] = None):
    """Get formatted warning tag."""
    if config is None:
        config = AppConfig()
    return '<ansiyellow><b>[warning]</b></ansiyellow>'

def info_tag(config: Optional[AppConfig] = None):
    """Get formatted info tag."""
    if config is None:
        config = AppConfig()
    return '<ansicyan><b>[info]</b></ansicyan>'
