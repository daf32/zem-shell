"""The prompt: format strings, modules, and the renderer that joins them."""

from zem.ui.prompt.format import FormatError, parse, render
from zem.ui.prompt.modules import (
    BUILTIN_MODULES,
    PromptContext,
    PromptModule,
    format_duration,
    format_path,
    format_path_display,
)
from zem.ui.prompt.renderer import PromptRenderer

__all__ = [
    "BUILTIN_MODULES",
    "FormatError",
    "PromptContext",
    "PromptModule",
    "PromptRenderer",
    "format_duration",
    "format_path",
    "format_path_display",
    "parse",
    "render",
]
