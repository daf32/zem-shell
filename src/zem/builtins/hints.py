from pathlib import Path
from typing import TYPE_CHECKING, Optional

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class HintsCommand(BaseCommand):
    help = "Inspect and install completion hint specs"
    usage = "hints [list|show|search|install|remove|update|validate|providers|reload] [name]"
    tags = ["builtin", "ui"]
    examples = [
        "hints                  - List the specs in use",
        "hints show git         - Show git's subcommands and flags",
        "hints search kube      - Search the registry",
        "hints install kubectl  - Install a spec from the registry",
        "hints update           - Update every installed spec",
        "hints remove kubectl   - Remove an installed spec",
        "hints validate ~/x.json - Check a spec you are writing",
        "hints providers        - List the value providers available",
    ]

    #: Explicit table, so a stray `hints registry` cannot reach a helper.
    _SUBCOMMANDS = {
        "list": "_list",
        "show": "_show",
        "search": "_search",
        "install": "_install",
        "remove": "_remove",
        "update": "_update",
        "validate": "_validate",
        "providers": "_providers",
        "reload": "_reload",
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
            self._write_err("hints: shell reference not available\n", stderr)
            return 1

        subcommand = args[0] if args else "list"
        handler = self._SUBCOMMANDS.get(subcommand)
        if handler is None:
            raise ArgumentError(self.name, args, reason=f"unknown subcommand '{subcommand}'")
        return getattr(self, handler)(args[1:], shell, stdout, stderr)

    # -- local specs -------------------------------------------------------

    def _list(self, args, shell, stdout, stderr) -> int:
        from zem.hints.spec import HintSpec

        registry = self._registry(shell)
        # One entry per spec: aliases register the same object twice.
        by_spec: dict[int, HintSpec] = {}
        for spec in registry.load().values():
            by_spec.setdefault(id(spec), spec)

        colors = shell.config.colors
        self._write("\n", stdout)
        for spec in sorted(by_spec.values(), key=lambda s: s.command):
            names = ", ".join(spec.names())
            self._print_colored([
                (colors.command, f"  {names:<22}"),
                ("", f"{spec.description[:40]:<42}"),
                (colors.comment, spec.origin),
            ], stdout)

        errors = registry.errors()
        if errors:
            self._write("\nSpecs that failed to load:\n", stdout)
            for path, messages in sorted(errors.items()):
                self._print_colored([
                    (colors.warning, f"  {path}\n"),
                    (colors.error, "    " + "\n    ".join(messages)),
                ], stdout)
        self._write("\n", stdout)
        return 0

    def _show(self, args, shell, stdout, stderr) -> int:
        name = self._get_arg(args, 0)
        if not name:
            raise ArgumentError(self.name, args, reason="expected <command>")
        spec = self._registry(shell).get(name)
        if spec is None:
            self._write_err(f"hints: no spec for '{name}'\n", stderr)
            return 1

        colors = shell.config.colors
        self._print_colored([
            (colors.command, f"\n{spec.command}"),
            ("", f"  {spec.description}"),
        ], stdout)
        self._print_colored([
            (colors.comment, f"  {spec.source_path} ({spec.origin})\n"),
        ], stdout)
        self._render_node(spec, shell, stdout, indent="  ")
        self._write("\n", stdout)
        return 0

    def _render_node(self, node, shell, stdout, indent: str) -> None:
        colors = shell.config.colors
        for option in getattr(node, "options", ()):
            if option.hidden:
                continue
            takes = " <value>" if option.value is not None else ""
            self._print_colored([
                (colors.variable, f"{indent}{', '.join(option.names)}{takes}"),
                (colors.comment, f"  {option.description}"),
            ], stdout)
        for child in getattr(node, "subcommands", ()):
            if child.hidden:
                continue
            self._print_colored([
                (colors.command, f"{indent}{child.name}"),
                ("", f"  {child.description}"),
            ], stdout)
            self._render_node(child, shell, stdout, indent + "  ")

    def _validate(self, args, shell, stdout, stderr) -> int:
        import json

        target = Path(self._get_arg(args, 0) or ".").expanduser()
        paths = sorted(target.glob("*.json")) if target.is_dir() else [target]
        if not paths:
            self._write_err(f"hints: no spec files in {target}\n", stderr)
            return 1

        from zem.hints.spec import SpecError, parse_spec

        failed = 0
        for path in paths:
            try:
                spec = parse_spec(json.loads(path.read_text(encoding="utf-8")))
            except OSError as exc:
                failed += 1
                self._write_err(f"{path}: {exc}\n", stderr)
            except ValueError as exc:
                failed += 1
                messages = exc.args[0] if isinstance(exc, SpecError) and \
                    isinstance(exc.args[0], list) else [str(exc)]
                self._write_err(f"{path}:\n", stderr)
                for message in messages:
                    self._write_err(f"  {message}\n", stderr)
            else:
                self._write(f"{path}: ok ({spec.command}, "
                            f"{len(spec.subcommands)} subcommands)\n", stdout)
        return 1 if failed else 0

    def _providers(self, args, shell, stdout, stderr) -> int:
        from zem.hints.providers import PROVIDERS

        for name in PROVIDERS.names():
            self._write(f"  {name}\n", stdout)
        return 0

    def _reload(self, args, shell, stdout, stderr) -> int:
        completer = getattr(getattr(shell, "session", None), "completer", None)
        if completer is not None and hasattr(completer, "invalidate_cache"):
            completer.invalidate_cache()
        else:
            from zem.hints import sources

            sources.clear_cache()
            self._registry(shell).reload()
        self._write("Hint specs reloaded\n", stdout)
        return 0

    # -- the registry ------------------------------------------------------

    def _search(self, args, shell, stdout, stderr) -> int:
        query = (self._get_arg(args, 0) or "").lower()
        entries = self._fetch_index(shell, stderr)
        if entries is None:
            return 1

        installed = {p.stem for p in self._user_dir(shell).glob("*.json")
             if not p.name.startswith(".")}
        colors = shell.config.colors
        matches = [
            e for e in entries
            if query in e.get("name", "").lower() or query in e.get("description", "").lower()
        ]
        if not matches:
            self._write(f"No spec matches '{query}'\n", stdout)
            return 0

        self._write("\n", stdout)
        for entry in sorted(matches, key=lambda e: e.get("name", "")):
            mark = " (installed)" if entry.get("name") in installed else ""
            self._print_colored([
                (colors.command, f"  {entry.get('name', ''):<16}"),
                ("", f"{entry.get('description', '')[:46]:<48}"),
                (colors.comment, f"{entry.get('subcommands', 0)} subcommands{mark}"),
            ], stdout)
        self._write("\n", stdout)
        return 0

    def _install(self, args, shell, stdout, stderr) -> int:
        if not args:
            raise ArgumentError(self.name, args, reason="expected <name>...")
        entries = self._fetch_index(shell, stderr)
        if entries is None:
            return 1
        by_name = {e.get("name"): e for e in entries}

        from zem.hints.registry_client import RegistryError, install

        base = shell.config.hints.registry_url
        target = self._user_dir(shell)
        colors = shell.config.colors
        failed = 0
        for name in args:
            entry = by_name.get(name)
            if entry is None:
                self._write_err(f"hints: '{name}' is not in the registry\n", stderr)
                failed += 1
                continue
            try:
                path = install(base, name, target, entry.get("sha256"))
            except RegistryError as exc:
                self._write_err(f"hints: {exc}\n", stderr)
                failed += 1
                continue
            self._print_colored([
                (colors.exit_code_ok, "✓ "),
                ("", f"{name} -> {path}"),
            ], stdout)

        if failed < len(args):
            self._reload([], shell, stdout, stderr)
            # A spec can run a command when TAB is pressed. Installing one is
            # the same act of trust as installing a plugin; say so out loud.
            self._print_colored([
                (colors.warning, "note: "),
                ("", "a spec may run commands to suggest values. "
                     "See 'hints show <command>'."),
            ], stdout)
        return 1 if failed else 0

    def _remove(self, args, shell, stdout, stderr) -> int:
        if not args:
            raise ArgumentError(self.name, args, reason="expected <name>...")
        target = self._user_dir(shell)
        failed = 0
        for name in args:
            path = target / f"{name}.json"
            if not path.exists():
                self._write_err(f"hints: '{name}' is not installed\n", stderr)
                failed += 1
                continue
            try:
                path.unlink()
            except OSError as exc:
                self._write_err(f"hints: cannot remove {path}: {exc}\n", stderr)
                failed += 1
                continue
            self._write(f"Removed {path}\n", stdout)
        if failed < len(args):
            self._reload([], shell, stdout, stderr)
        return 1 if failed else 0

    def _update(self, args, shell, stdout, stderr) -> int:
        target = self._user_dir(shell)
        names = args or sorted(p.stem for p in target.glob("*.json")
                       if not p.name.startswith("."))
        if not names:
            self._write("No specs installed from the registry\n", stdout)
            return 0

        entries = self._fetch_index(shell, stderr, refresh=True)
        if entries is None:
            return 1
        by_name = {e.get("name"): e for e in entries}

        import hashlib

        from zem.hints.registry_client import RegistryError, install

        base = shell.config.hints.registry_url
        changed = failed = 0
        for name in names:
            entry = by_name.get(name)
            if entry is None:
                self._write(f"  {name}: not in the registry, left alone\n", stdout)
                continue
            path = target / f"{name}.json"
            if path.exists() and entry.get("sha256"):
                current = hashlib.sha256(path.read_bytes()).hexdigest()
                if current == entry["sha256"]:
                    continue
            try:
                install(base, name, target, entry.get("sha256"))
            except RegistryError as exc:
                self._write_err(f"hints: {exc}\n", stderr)
                failed += 1
                continue
            changed += 1
            self._write(f"  {name}: updated\n", stdout)

        self._write(f"{changed} updated, {len(names) - changed - failed} already current\n",
                    stdout)
        if changed:
            self._reload([], shell, stdout, stderr)
        return 1 if failed else 0

    # -- helpers -----------------------------------------------------------

    def _registry(self, shell):
        completer = getattr(getattr(shell, "session", None), "completer", None)
        existing = getattr(completer, "hints", None)
        if existing is not None:
            return existing
        from zem.hints.loader import HintRegistry

        return HintRegistry(shell.config)

    def _user_dir(self, shell) -> Path:
        return Path(shell.config.hints.user_dir).expanduser()

    def _fetch_index(self, shell, stderr, refresh: bool = False) -> Optional[list]:
        from zem.hints.registry_client import RegistryError, cache_path_for, fetch_index

        try:
            return fetch_index(shell.config.hints.registry_url,
                               cache_path_for(shell.config.hints.user_dir),
                               refresh=refresh)
        except RegistryError as exc:
            self._write_err(f"hints: {exc}\n", stderr)
            return None
