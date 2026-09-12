from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class PluginCommand(BaseCommand):
    help = "Inspect and manage plugins"
    usage = "plugin [list|info|enable|disable] [name]"
    tags = ["builtin"]
    examples = [
        "plugin              - List the plugins that were found",
        "plugin info weather - Show what one plugin provides",
        "plugin disable foo  - Stop loading it (takes effect next start)",
        "plugin enable foo   - Load it again",
    ]

    _SUBCOMMANDS = {
        "list": "_list",
        "info": "_info",
        "enable": "_enable",
        "disable": "_disable",
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
            self._write_err("plugin: shell reference not available\n", stderr)
            return 1

        subcommand = args[0] if args else "list"
        handler = self._SUBCOMMANDS.get(subcommand)
        if handler is None:
            raise ArgumentError(self.name, args, reason=f"unknown subcommand '{subcommand}'")
        return getattr(self, handler)(args[1:], shell, stdout, stderr)

    def _list(self, args, shell, stdout, stderr) -> int:
        records = sorted(shell.plugins.loaded, key=lambda r: r.name)
        if not records:
            self._write("No plugins found\n", stdout)
            return 0

        colors = shell.config.colors
        self._write("\n", stdout)
        for record in records:
            if record.error:
                status, colour = "failed", colors.error
            elif not record.enabled:
                status, colour = "disabled", colors.comment
            else:
                status, colour = "active", colors.exit_code_ok
            self._print_colored([
                (colors.command, f"  {record.name:<18}"),
                (colour, f"{status:<10}"),
                (colors.comment, f"{record.origin:<12}"),
                ("", record.description[:40]),
            ], stdout)
            if record.error:
                self._print_colored([(colors.error, f"      {record.error}")], stdout)
        self._write("\n", stdout)
        return 0

    def _info(self, args, shell, stdout, stderr) -> int:
        name = self._get_arg(args, 0)
        if not name:
            raise ArgumentError(self.name, args, reason="expected <name>")
        record = next((r for r in shell.plugins.loaded if r.name == name), None)
        if record is None:
            self._write_err(f"plugin: '{name}' not found\n", stderr)
            return 1

        colors = shell.config.colors
        self._print_colored([
            (colors.command, f"\n{record.name}"),
            ("", f" {record.version}"),
            (colors.comment, f"  ({record.origin})"),
        ], stdout)
        if record.description:
            self._write(f"  {record.description}\n", stdout)
        self._write(f"  source: {record.source}\n", stdout)
        if record.error:
            self._print_colored([(colors.error, f"  error: {record.error}")], stdout)
        if not record.enabled:
            self._print_colored([(colors.comment, "  disabled")], stdout)

        plugin = record.plugin
        if plugin is not None:
            for label, values in (
                ("commands", [c.__name__ for c in _safe(plugin.commands)]),
                ("hint providers", sorted(_safe(plugin.hint_providers))),
                ("completers", sorted(_safe(plugin.completers))),
                ("hint specs", list(_safe(plugin.hint_specs))),
                ("themes", list(_safe(plugin.themes))),
            ):
                if values:
                    self._write(f"  {label}: {', '.join(str(v) for v in values)}\n", stdout)
        self._write("\n", stdout)
        return 0

    def _enable(self, args, shell, stdout, stderr) -> int:
        return self._toggle(args, shell, stdout, stderr, disable=False)

    def _disable(self, args, shell, stdout, stderr) -> int:
        return self._toggle(args, shell, stdout, stderr, disable=True)

    def _toggle(self, args, shell, stdout, stderr, disable: bool) -> int:
        name = self._get_arg(args, 0)
        if not name:
            raise ArgumentError(self.name, args, reason="expected <name>")

        known = {r.name for r in shell.plugins.loaded}
        if disable and name not in known:
            self._write_err(f"plugin: '{name}' not found\n", stderr)
            return 1

        from zem.config.settings import get_config_path
        from zem.config.store import update_raw

        def mutate(data: dict) -> None:
            disabled = list(data.get("disabled_plugins", shell.config.disabled_plugins))
            if disable and name not in disabled:
                disabled.append(name)
            elif not disable and name in disabled:
                disabled.remove(name)
            data["disabled_plugins"] = sorted(disabled)

        try:
            update_raw(get_config_path(), mutate)
        except OSError as exc:
            self._write_err(f"plugin: cannot write the config: {exc}\n", stderr)
            return 1

        mutate_target = list(shell.config.disabled_plugins)
        if disable and name not in mutate_target:
            mutate_target.append(name)
        elif not disable and name in mutate_target:
            mutate_target.remove(name)
        shell.config.disabled_plugins = sorted(mutate_target)

        word = "disabled" if disable else "enabled"
        self._write(f"Plugin '{name}' {word}; restart zem for it to take effect\n", stdout)
        return 0


def _safe(hook):
    """Call a plugin hook for display; a broken one shows as nothing."""
    try:
        return hook() or ()
    except Exception:
        return ()
