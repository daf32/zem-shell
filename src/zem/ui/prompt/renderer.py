"""Turning a format string plus modules into a prompt."""

from __future__ import annotations

import logging
from typing import Optional

from zem.ui.prompt import format as fmt
from zem.ui.prompt.modules import BUILTIN_MODULES, PromptContext, PromptModule

log = logging.getLogger(__name__)


class PromptRenderer:
    """Holds the available modules and renders a format string with them."""

    def __init__(self, shell, extra: Optional[dict] = None):
        self.shell = shell
        self.modules: dict = {cls.name: cls() for cls in BUILTIN_MODULES}
        if extra:
            # Plugins go last, so one may replace a builtin module.
            self.modules.update(extra)
        self._parsed: dict = {}
        self._warned: set = set()

    # -- public ------------------------------------------------------------

    def render(self, format_string: str, ctx: PromptContext,
               colored: bool = True) -> object:
        """Render `format_string`; a plain string when `colored` is false."""
        try:
            nodes = self._parse(format_string)
        except fmt.FormatError as exc:
            self._warn(format_string, f"bad prompt format: {exc}")
            return [] if colored else ""

        fragments = fmt.render(
            nodes,
            resolve=lambda name: self._render_module(name, ctx),
            style_map=self._style,
        )
        if colored:
            return fragments
        return "".join(text for _style, text in fragments)

    # -- internals ---------------------------------------------------------

    def _parse(self, text: str) -> list:
        if text not in self._parsed:
            self._parsed[text] = fmt.parse(text)
        return self._parsed[text]

    def _render_module(self, name: str, ctx: PromptContext) -> Optional[list]:
        module = self.modules.get(name)
        if module is None:
            self._warn(name, f"unknown prompt module {name!r}")
            return None

        settings = self._settings(name)
        if settings.get("disabled"):
            return None

        try:
            variables = module.variables(ctx)
        except Exception as exc:
            # A module's bad day must not cost the user their prompt.
            self._warn(name, f"prompt module {name!r} failed: {exc}")
            return None
        if variables is None:
            return None

        module_format = settings.get("format") or module.default_format
        style = settings.get("style") or self._module_style(module, ctx)
        try:
            nodes = self._parse(module_format)
        except fmt.FormatError as exc:
            self._warn(f"{name}:format", f"bad format for module {name!r}: {exc}")
            return None

        def resolve(variable: str):
            if variable == "style":
                return None  # only meaningful inside a style, handled below
            return variables.get(variable)

        def style_map(written: str) -> str:
            # A style written as `$style` means "this module's style"; the
            # parser hands it over with the dollar still attached.
            if written.lstrip("$") == "style":
                return self._style(style)
            return self._style(written)

        return fmt.render(nodes, resolve=resolve, style_map=style_map)

    def _module_style(self, module: PromptModule, ctx: PromptContext) -> str:
        """A module may choose its style from context (exit code colour)."""
        chooser = getattr(module, "style_for", None)
        if chooser is not None:
            try:
                return chooser(ctx)
            except Exception:
                pass
        return module.default_style

    def _settings(self, name: str) -> dict:
        modules = getattr(self.shell.config.prompt, "modules", {})
        value = modules.get(name) if isinstance(modules, dict) else None
        return value if isinstance(value, dict) else {}

    #: Style classes the shell defines in `_build_style` beyond the theme's
    #: own colour keys.
    SHELL_STYLE_CLASSES = frozenset({
        "git_branch", "venv", "duration", "rprompt", "path-notfound", "flag",
        "number", "url", "auto-suggestion",
    })

    def _style(self, style: str) -> str:
        """Map a style name to something prompt_toolkit understands.

        A theme colour key (`path`) or a style class the shell defines
        (`git_branch`) becomes `class:...`, so themes keep working. Anything
        else is passed straight through, which is what makes `bold green`
        and `fg:#ff8800` work.
        """
        if not style:
            return ""
        if style in self.SHELL_STYLE_CLASSES or hasattr(self.shell.config.colors, style):
            return f"class:{style}"
        return style

    def _warn(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            log.warning("%s", message)
