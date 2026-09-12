import sys
from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class PluginCommand(BaseCommand):
    help = "Inspect and manage plugins"
    usage = "plugin [list|info|install|remove|packages|enable|disable] [name]"
    tags = ["builtin"]
    examples = [
        "plugin                     - List the plugins that were found",
        "plugin info weather        - Show what one plugin provides",
        "plugin install zem-plugin-x - Install a plugin package",
        "plugin remove zem-plugin-x  - Uninstall it",
        "plugin packages            - Installed packages that provide plugins",
        "plugin disable foo         - Stop loading it (takes effect next start)",
        "plugin enable foo          - Load it again",
    ]

    #: Installing shells out and asks for confirmation on stdin.
    main_thread_only = True

    _SUBCOMMANDS = {
        "list": "_list",
        "info": "_info",
        "install": "_install",
        "remove": "_remove",
        "packages": "_packages",
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

    # -- installing --------------------------------------------------------

    def _install(self, args, shell, stdout, stderr) -> int:
        packages, assume_yes = self._split_yes(args)
        if not packages:
            raise ArgumentError(self.name, args, reason="expected <package>...")
        return self._change(shell, packages, assume_yes, stdout, stderr, removing=False)

    def _remove(self, args, shell, stdout, stderr) -> int:
        names, assume_yes = self._split_yes(args)
        if not names:
            raise ArgumentError(self.name, args, reason="expected <package>...")

        from zem.plugin.installer import find_distribution_for

        # Accept either the plugin's name or its distribution's.
        packages = []
        for name in names:
            packages.append(find_distribution_for(name) or name)
        return self._change(shell, packages, assume_yes, stdout, stderr, removing=True)

    def _change(self, shell, packages, assume_yes, stdout, stderr, removing: bool) -> int:
        from zem.plugin.installer import InstallError, detect_environment, run, validate

        try:
            validate(packages)
        except InstallError as exc:
            self._write_err(f"plugin: {exc}\n", stderr)
            return 2

        environment = detect_environment()
        if not environment.can_install:
            self._write_err(f"plugin: {environment.reason}\n", stderr)
            return 1

        command = (environment.uninstall_command(packages) if removing
                   else environment.install_command(packages))
        colors = shell.config.colors
        verb = "Remove" if removing else "Install"
        self._print_colored([
            ("", f"{verb} {', '.join(packages)} via "),
            (colors.info, environment.description),
        ], stdout)
        self._print_colored([(colors.comment, f"  {' '.join(command)}")], stdout)
        if not removing:
            # A plugin runs in your shell, with your permissions, on every
            # command. That is worth one sentence before installing one.
            self._print_colored([
                (colors.warning, "  note: "),
                ("", "a plugin runs code in your shell on every command"),
            ], stdout)

        if not assume_yes and not self._confirm(stdout, stderr):
            self._write("Cancelled\n", stdout)
            return 1

        try:
            code = run(command, stdout, stderr)
        except InstallError as exc:
            self._write_err(f"plugin: {exc}\n", stderr)
            return 1
        if code != 0:
            self._write_err(f"plugin: {command[0]} exited with {code}\n", stderr)
            return code

        done = "removed" if removing else "installed"
        self._write(f"{', '.join(packages)} {done}; restart zem to pick it up\n", stdout)
        return 0

    def _packages(self, args, shell, stdout, stderr) -> int:
        from zem.plugin.installer import installed_distributions

        found = installed_distributions()
        if not found:
            self._write("No installed package provides a zem plugin\n", stdout)
            return 0
        colors = shell.config.colors
        self._write("\n", stdout)
        for name, version in found:
            self._print_colored([
                (colors.command, f"  {name:<28}"),
                (colors.comment, version),
            ], stdout)
        self._write("\n", stdout)
        return 0

    @staticmethod
    def _split_yes(args) -> tuple:
        packages = [a for a in args if a not in ("-y", "--yes")]
        return packages, len(packages) != len(args)

    def _confirm(self, stdout, stderr) -> bool:
        stream = stdout or sys.stdout
        if not getattr(sys.stdin, "isatty", lambda: False)():
            self._write_err(
                "plugin: refusing to install without a terminal to confirm on; "
                "pass -y if you meant it\n",
                stderr,
            )
            return False
        stream.write("Proceed? [y/N] ")
        stream.flush()
        return self._input().strip().lower() in ("y", "yes")

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
