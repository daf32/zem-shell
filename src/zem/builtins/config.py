import os
from typing import Any

from zem.builtins.base import BaseCommand
from zem.core.context import ExecutionContext
from zem.errors.input_error import ArgumentError


class ConfigCommand(BaseCommand):
    name = "config"
    help = "Manage shell configuration"
    usage = "config [list|get|set|unset|reload|path|edit] [key] [value]"
    tags = ["builtin", "core"]
    examples = [
        "config list                    - Show all settings",
        "config get input.prompt        - Get prompt symbol",
        "config set input.prompt '>'    - Change prompt symbol (validated)",
        "config unset input.prompt      - Remove a key (back to default)",
        "config reload                  - Reload config from file",
        "config path                    - Show config file location",
        "config edit                    - Open config in $EDITOR",
    ]

    def execute(
        self,
        args: list[str],
        context: ExecutionContext,
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        from zem.config.settings import get_config_path
        from zem.config.store import read_raw

        CONFIG_PATH = get_config_path()

        if not args:
            self._write(f"Usage: {self.usage}\n", stdout)
            self._write("Subcommands: list, get, set, unset, reload, path, edit\n", stdout)
            return 0

        command = args[0].lower()

        # Load current raw JSON
        try:
            data = read_raw(CONFIG_PATH)
        except (ValueError, OSError) as e:
            self._write_err(f"config: cannot read {CONFIG_PATH}: {e}\n", stderr)
            return 1

        if command == "list":
            self._print_dict(data, stdout=stdout)
            return 0

        if command == "get":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected KEY")
            key = args[1]
            val = self._get_value(data, key)
            if val is not None:
                self._write(f"{val}\n", stdout)
                return 0
            self._write_err(f"config: key '{key}' not found\n", stderr)
            return 1

        if command == "set":
            if len(args) < 3:
                raise ArgumentError(self.name, args, reason="expected KEY VALUE")
            key = args[1]
            value = self._infer_type(" ".join(args[2:]))
            return self._set(context, CONFIG_PATH, key, value, stdout, stderr)

        if command == "unset":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected KEY")
            return self._unset(CONFIG_PATH, args[1], stdout, stderr)

        if command == "reload":
            return self._reload_config(context, stdout)

        if command == "path":
            self._write(f"{CONFIG_PATH}\n", stdout)
            return 0

        if command == "edit":
            import shlex
            import subprocess
            editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
            # Allow `EDITOR="vim -p"` style values without going through a shell.
            editor_argv = shlex.split(editor)
            if not editor_argv:
                self._write("✗ $EDITOR is empty\n", stdout)
                return 1
            self._write(f"Opening {CONFIG_PATH} with {editor}...\n", stdout)
            try:
                subprocess.run([*editor_argv, CONFIG_PATH], check=False)
            except FileNotFoundError:
                self._write(f"✗ Editor '{editor_argv[0]}' not found\n", stdout)
                return 1
            # Reload after editing
            self._write("Reloading configuration...\n", stdout)
            return self._reload_config(context, stdout)

        raise ArgumentError(self.name, command, reason="unknown subcommand")

    def _validated(self, data: dict, stderr) -> bool:
        """Reject a document the shell could not start with."""
        from pydantic import ValidationError

        from zem.config.settings import AppConfig, format_validation_error

        try:
            AppConfig.model_validate(data)
        except ValidationError as e:
            self._write_err("config: invalid value, nothing written:\n", stderr)
            for line in format_validation_error(e):
                self._write_err(f"  {line}\n", stderr)
            return False
        return True

    def _set(self, context, path: str, key: str, value: Any, stdout, stderr) -> int:
        from zem.config.store import read_raw, write_raw

        # Validate on a copy first so an invalid value never reaches disk.
        candidate = read_raw(path)
        if not self._set_value(candidate, key, value):
            self._write_err(f"config: cannot set '{key}': parent is not a section\n", stderr)
            return 1
        if not self._validated(candidate, stderr):
            return 1
        write_raw(path, candidate)
        self._write(f"✓ Set '{key}' = {value!r}\n", stdout)
        self._hot_reload_setting(context, key, value, stdout)
        return 0

    def _unset(self, path: str, key: str, stdout, stderr) -> int:
        from zem.config.store import read_raw, write_raw

        candidate = read_raw(path)
        keys = key.split(".")
        curr = candidate
        for k in keys[:-1]:
            if not isinstance(curr, dict) or k not in curr:
                self._write_err(f"config: key '{key}' not found\n", stderr)
                return 1
            curr = curr[k]
        if not isinstance(curr, dict) or keys[-1] not in curr:
            self._write_err(f"config: key '{key}' not found\n", stderr)
            return 1
        del curr[keys[-1]]
        if not self._validated(candidate, stderr):
            return 1
        write_raw(path, candidate)
        self._write(f"✓ Unset '{key}' (default applies after 'config reload')\n", stdout)
        return 0

    def _reload_config(self, context: ExecutionContext, stdout) -> int:
        """Reload configuration from file and apply changes.

        Returns the exit code (0 on success, 1 on failure).
        """
        from zem.config.settings import AppConfig

        if not hasattr(context, '_shell') or context._shell is None:
            self._write("✗ Cannot reload: shell reference not found\n", stdout)
            return 1

        shell = context._shell

        try:
            # Create new config instance (reads from file)
            new_config = AppConfig()

            # Update shell config
            shell.config = new_config

            # Rebuild style
            shell.style = shell._build_style()
            if hasattr(shell, 'session') and shell.session:
                shell.session.style = shell.style

            # Invalidate caches
            session = getattr(shell, "session", None)
            if session is None:
                self._write("✓ Configuration reloaded successfully\n", stdout)
                return 0
            if hasattr(shell.session, 'lexer') and shell.session.lexer:
                lexer = shell.session.lexer
                if hasattr(lexer, 'invalidate_cache'):
                    lexer.invalidate_cache()

            if hasattr(shell.session, 'completer') and shell.session.completer:
                completer = shell.session.completer
                if hasattr(completer, 'invalidate_cache'):
                    completer.invalidate_cache()

            self._write("✓ Configuration reloaded successfully\n", stdout)
            return 0

        except Exception as e:
            self._write(f"✗ Failed to reload config: {e}\n", stdout)
            return 1

    def _hot_reload_setting(self, context: ExecutionContext, key: str, value: Any, stdout):
        """Try to hot-reload a specific setting."""
        if not hasattr(context, '_shell') or context._shell is None:
            return
        
        shell = context._shell
        parts = key.split('.')
        
        # Handle color changes
        if parts[0] == "colors" and len(parts) == 2:
            color_name = parts[1]
            if hasattr(shell.config.colors, color_name):
                setattr(shell.config.colors, color_name, value)
                shell.style = shell._build_style()
                if hasattr(shell, 'session') and shell.session:
                    shell.session.style = shell.style
                self._write("  (style updated)\n", stdout)
                return
        
        # Handle input settings
        if parts[0] == "input" and len(parts) == 2:
            setting_name = parts[1]
            if hasattr(shell.config.input, setting_name):
                setattr(shell.config.input, setting_name, value)
                self._write("  (setting applied)\n", stdout)
                return
        
        # Default: suggest reload
        self._write("  (use 'config reload' to apply)\n", stdout)

    def _print_dict(self, d: dict, prefix: str = "", stdout=None):
        for k, v in d.items():
            if isinstance(v, dict):
                self._print_dict(v, f"{prefix}{k}.", stdout)
            else:
                self._write(f"{prefix}{k} = {v}\n", stdout)

    def _get_value(self, data: dict, key: str) -> Any:
        keys = key.split('.')
        curr = data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return None
        return curr

    def _set_value(self, data: dict, key: str, value: Any) -> bool:
        keys = key.split('.')
        curr = data
        for k in keys[:-1]:
            if k not in curr:
                # Create dict if missing
                curr[k] = {}
            if not isinstance(curr[k], dict):
                # Conflict: trying to nest into a non-dict
                return False
            curr = curr[k]
        
        last_key = keys[-1]
        curr[last_key] = value
        return True

    def _infer_type(self, value: str) -> Any:
        value_lower = value.lower()
        if value_lower == "true":
            return True
        if value_lower == "false":
            return False
        if value_lower == "null":
            return None
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value
