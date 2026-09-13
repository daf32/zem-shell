import os
import sys
from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class PromptCommand(BaseCommand):
    help = "Look at, preview and configure the prompt"
    usage = "prompt [show|list|preview|set|configure|reset] [name]"
    tags = ["builtin", "ui"]
    examples = [
        "prompt              - Show the current format, with a preview",
        "prompt list         - Preview every preset",
        "prompt set pure     - Switch to a preset",
        "prompt configure    - Answer a few questions instead",
        "prompt reset        - Back to the default",
    ]

    #: `configure` asks questions on stdin.
    main_thread_only = True

    _SUBCOMMANDS = {
        "show": "_show",
        "list": "_list",
        "preview": "_preview",
        "set": "_set",
        "configure": "_configure",
        "reset": "_reset",
    }

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err("prompt: shell reference not available\n", stderr)
            return 1

        subcommand = args[0] if args else "show"
        handler = self._SUBCOMMANDS.get(subcommand)
        if handler is None:
            raise ArgumentError(self.name, args, reason=f"unknown subcommand '{subcommand}'")
        return getattr(self, handler)(args[1:], shell, stdout, stderr)

    # -- looking -----------------------------------------------------------

    def _show(self, args, shell, stdout, stderr) -> int:
        colors = shell.config.colors
        self._write("\n", stdout)
        self._print_colored([
            (colors.comment, "  format       "),
            ("", shell.config.prompt.format.replace("\n", "\\n")),
        ], stdout)
        self._print_colored([
            (colors.comment, "  right_format "),
            ("", shell.config.prompt.right_format.replace("\n", "\\n")),
        ], stdout)
        self._write("\n  looks like:\n\n    ", stdout)
        self._render_sample(shell, shell.config.prompt.format,
                            shell.config.prompt.modules, stdout)
        self._write("\n\n", stdout)
        return 0

    def _list(self, args, shell, stdout, stderr) -> int:
        presets = self._presets(shell)
        colors = shell.config.colors
        current = shell.config.prompt.format
        self._write("\n", stdout)
        for name, preset in sorted(presets.items()):
            mark = " (current)" if preset.format == current else ""
            self._print_colored([
                (colors.command, f"  {name}"),
                (colors.comment, f"{mark}  {preset.description}"),
            ], stdout)
            self._write("    ", stdout)
            self._render_sample(shell, preset.format, preset.modules, stdout)
            self._write("\n", stdout)
        self._write("\n", stdout)
        return 0

    def _preview(self, args, shell, stdout, stderr) -> int:
        name = self._get_arg(args, 0)
        if not name:
            raise ArgumentError(self.name, args, reason="expected <preset>")
        preset = self._presets(shell).get(name)
        if preset is None:
            self._write_err(f"prompt: no preset named '{name}'\n", stderr)
            return 1
        self._write("\n    ", stdout)
        self._render_sample(shell, preset.format, preset.modules, stdout)
        self._write("\n\n", stdout)
        return 0

    # -- changing ----------------------------------------------------------

    def _set(self, args, shell, stdout, stderr) -> int:
        name = self._get_arg(args, 0)
        if not name:
            raise ArgumentError(self.name, args, reason="expected <preset>")
        preset = self._presets(shell).get(name)
        if preset is None:
            self._write_err(
                f"prompt: no preset named '{name}' (try 'prompt list')\n", stderr)
            return 1
        return self._apply(preset.as_config(), shell, stdout, stderr, f"Prompt set to '{name}'")

    def _reset(self, args, shell, stdout, stderr) -> int:
        from zem.config.settings import PromptSettings

        defaults = PromptSettings()
        return self._apply(
            {"format": defaults.format, "right_format": defaults.right_format, "modules": {}},
            shell, stdout, stderr, "Prompt reset to the default",
        )

    def _apply(self, values: dict, shell, stdout, stderr, message: str) -> int:
        from zem.config.settings import get_config_path
        from zem.config.store import update_raw

        def mutate(data: dict) -> None:
            section = data.setdefault("prompt", {})
            section.update(values)

        try:
            update_raw(get_config_path(), mutate)
        except OSError as exc:
            self._write_err(f"prompt: cannot write the config: {exc}\n", stderr)
            return 1

        # Live, so the next prompt already looks different.
        shell.config.prompt.format = values["format"]
        shell.config.prompt.right_format = values.get("right_format", "")
        shell.config.prompt.modules = values.get("modules", {})
        shell.prompt_renderer._parsed.clear()

        self._print_colored([
            (shell.config.colors.exit_code_ok, "✓ "), ("", message),
        ], stdout)
        return 0

    # -- the wizard --------------------------------------------------------

    def _configure(self, args, shell, stdout, stderr) -> int:
        if not getattr(sys.stdin, "isatty", lambda: False)():
            self._write_err(
                "prompt: configure needs a terminal; use 'prompt set <preset>'\n", stderr)
            return 1

        presets = self._presets(shell)
        names = sorted(presets)
        colors = shell.config.colors

        self._write("\n  Pick a starting point:\n\n", stdout)
        for index, name in enumerate(names, start=1):
            self._print_colored([
                (colors.command, f"  {index}) {name:<12}"),
                (colors.comment, presets[name].description),
            ], stdout)
            self._write("       ", stdout)
            self._render_sample(shell, presets[name].format, presets[name].modules, stdout)
            self._write("\n", stdout)

        choice = self._ask(f"\n  Which one? [1-{len(names)}, q to cancel] ", stdout)
        if choice.lower() in ("q", "quit", ""):
            self._write("Cancelled\n", stdout)
            return 1
        if not choice.isdigit() or not 1 <= int(choice) <= len(names):
            self._write_err(f"prompt: '{choice}' is not one of the options\n", stderr)
            return 2

        preset = presets[names[int(choice) - 1]]
        modules = dict(preset.modules)

        # A few yes/no questions, each one just disabling a module.
        for module, question in (
            ("git", "Show the git branch?"),
            ("venv", "Show the Python virtualenv?"),
            ("duration", "Show how long the last command took?"),
            ("time", "Show the clock on the right?"),
        ):
            if f"${module}" not in preset.format + preset.right_format:
                continue
            if not self._ask_yes_no(f"  {question}", stdout):
                modules.setdefault(module, {})["disabled"] = True

        symbol = self._ask(
            f"  Prompt character? [{shell.config.input.prompt}] ", stdout).strip()

        self._write("\n  Result:\n\n    ", stdout)
        self._render_sample(shell, preset.format, modules, stdout)
        self._write("\n\n", stdout)

        if not self._ask_yes_no("  Keep it?", stdout, default=True):
            self._write("Cancelled\n", stdout)
            return 1

        if symbol:
            shell.config.input.prompt = symbol
            self._save_symbol(symbol, stderr)

        values = dict(preset.as_config())
        values["modules"] = modules
        return self._apply(values, shell, stdout, stderr, f"Prompt set to '{preset.name}'")

    def _save_symbol(self, symbol: str, stderr) -> None:
        from zem.config.settings import get_config_path
        from zem.config.store import update_raw

        def mutate(data: dict) -> None:
            data.setdefault("input", {})["prompt"] = symbol

        try:
            update_raw(get_config_path(), mutate)
        except OSError as exc:
            self._write_err(f"prompt: cannot write the config: {exc}\n", stderr)

    # -- helpers -----------------------------------------------------------

    def _presets(self, shell) -> dict:
        from zem.ui.prompt.presets import load_presets

        return load_presets()

    def _render_sample(self, shell, format_string: str, modules: dict, stdout) -> None:
        """Draw a format string with made-up values, so it reads anywhere."""
        from zem.ui.prompt import PromptContext

        saved = shell.config.prompt.modules
        shell.config.prompt.modules = modules or {}
        try:
            ctx = PromptContext(shell=shell, cwd=os.getcwd(), exit_code=0, duration=1.2)
            fragments = shell.prompt_renderer.render(format_string, ctx, sample=True)
        finally:
            shell.config.prompt.modules = saved
            shell.prompt_renderer._parsed.clear()
        # Indent the second line of a two-line prompt so the preview lines up.
        self._print_colored(
            [(style, text.replace("\n", "\n    ")) for style, text in fragments], stdout)

    def _ask(self, question: str, stdout) -> str:
        stream = stdout or sys.stdout
        stream.write(question)
        stream.flush()
        return self._input()

    def _ask_yes_no(self, question: str, stdout, default: bool = True) -> bool:
        suffix = " [Y/n] " if default else " [y/N] "
        answer = self._ask(question + suffix, stdout).strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes")
