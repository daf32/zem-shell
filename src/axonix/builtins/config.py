import json
import os
from typing import Any, List, Optional
from axonix.builtins.base import BaseCommand
from axonix.core.context import ExecutionContext
from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document


class ConfigCompleter(BaseArgCompleter):
    """Completer for config command with subcommand and key completion."""
    
    SUBCOMMANDS = {
        "list": "List all configuration values",
        "get": "Get a configuration value",
        "set": "Set a configuration value",
        "reload": "Reload configuration from file",
        "path": "Show configuration file path",
        "edit": "Open configuration in editor",
    }
    
    def __init__(self, config_data: dict):
        self.config_data = config_data

    def _get_keys(self, data: dict, prefix: str = "") -> List[str]:
        keys = []
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(self._get_keys(v, full_key))
            else:
                keys.append(full_key)
        return keys

    def get_completions(self, document: Document, parts: List[str], word_before: str):
        ends_with_space = document.text_before_cursor.endswith(" ")
        
        # Subcommands completion
        if len(parts) == 1 and ends_with_space:
            for cmd, desc in sorted(self.SUBCOMMANDS.items()):
                yield Completion(cmd, start_position=0, display_meta=desc)
            return
        
        if len(parts) == 2 and not ends_with_space:
            current_subcmd = parts[1]
            for cmd, desc in sorted(self.SUBCOMMANDS.items()):
                if cmd.startswith(current_subcmd):
                    yield Completion(cmd, start_position=-len(current_subcmd), display_meta=desc)
            return

        # Key completion for get/set
        if len(parts) >= 2:
            subcmd = parts[1]
            if subcmd in ["get", "set"]:
                if (len(parts) == 2 and ends_with_space) or (len(parts) == 3 and not ends_with_space):
                    all_keys = self._get_keys(self.config_data)
                    current_input = parts[2] if len(parts) == 3 else ""
                    
                    for key in sorted(all_keys):
                        if key.lower().startswith(current_input.lower()):
                            yield Completion(key, start_position=-len(current_input))


class ConfigCommand(BaseCommand):
    name = "config"
    help = "Manage shell configuration"
    usage = "config [list|get|set|reload|path|edit] [key] [value]"
    tags = ["builtin", "core"]
    examples = [
        "config list                    - Show all settings",
        "config get input.prompt        - Get prompt symbol",
        "config set input.prompt '>'    - Change prompt symbol",
        "config reload                  - Reload config from file",
        "config path                    - Show config file location",
        "config edit                    - Open config in $EDITOR",
    ]

    def get_completer(self):
        from axonix.config.settings import CONFIG_PATH
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            return ConfigCompleter(data)
        except Exception:
            return ConfigCompleter({})

    def execute(self, args: list[str], context: ExecutionContext, stdin=None, stdout=None):
        from axonix.config.settings import CONFIG_PATH, AppConfig
        
        if not args:
            self._write(f"Usage: {self.usage}\n", stdout)
            self._write("Subcommands: list, get, set, reload, path, edit\n", stdout)
            return

        command = args[0].lower()
        
        # Load current raw JSON
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
        else:
            data = {}

        if command == "list":
            self._print_dict(data, stdout=stdout)
            
        elif command == "get":
            if len(args) < 2:
                self._write("Usage: config get <key>\n", stdout)
                return
            key = args[1]
            val = self._get_value(data, key)
            if val is not None:
                self._write(f"{val}\n", stdout)
            else:
                self._write(f"Key '{key}' not found.\n", stdout)
                context.last_exit_code = 1
                
        elif command == "set":
            if len(args) < 3:
                self._write("Usage: config set <key> <value>\n", stdout)
                return
            key = args[1]
            value_str = " ".join(args[2:])
            
            value = self._infer_type(value_str)
            
            if self._set_value(data, key, value):
                with open(CONFIG_PATH, "w") as f:
                    json.dump(data, f, indent=4)
                
                self._write(f"✓ Set '{key}' = {repr(value)}\n", stdout)
                
                # Hot reload the setting if possible
                self._hot_reload_setting(context, key, value, stdout)
            else:
                self._write(f"✗ Failed to set '{key}'\n", stdout)
                context.last_exit_code = 1
        
        elif command == "reload":
            self._reload_config(context, stdout)
        
        elif command == "path":
            self._write(f"{CONFIG_PATH}\n", stdout)
        
        elif command == "edit":
            import shlex
            import subprocess
            editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
            # Allow `EDITOR="vim -p"` style values without going through a shell.
            editor_argv = shlex.split(editor)
            if not editor_argv:
                self._write("✗ $EDITOR is empty\n", stdout)
                context.last_exit_code = 1
                return
            self._write(f"Opening {CONFIG_PATH} with {editor}...\n", stdout)
            try:
                subprocess.run([*editor_argv, CONFIG_PATH], check=False)
            except FileNotFoundError:
                self._write(f"✗ Editor '{editor_argv[0]}' not found\n", stdout)
                context.last_exit_code = 1
                return
            # Reload after editing
            self._write("Reloading configuration...\n", stdout)
            self._reload_config(context, stdout)
        
        else:
            self._write(f"Unknown subcommand: {command}\n", stdout)
            self._write(f"Usage: {self.usage}\n", stdout)
            context.last_exit_code = 1

    def _reload_config(self, context: ExecutionContext, stdout):
        """Reload configuration from file and apply changes."""
        from axonix.config.settings import AppConfig
        
        if not hasattr(context, '_shell') or context._shell is None:
            self._write("✗ Cannot reload: shell reference not found\n", stdout)
            return
        
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
            if hasattr(shell.session, 'lexer') and shell.session.lexer:
                lexer = shell.session.lexer
                if hasattr(lexer, 'invalidate_cache'):
                    lexer.invalidate_cache()
            
            if hasattr(shell.session, 'completer') and shell.session.completer:
                completer = shell.session.completer
                if hasattr(completer, 'invalidate_cache'):
                    completer.invalidate_cache()
            
            self._write("✓ Configuration reloaded successfully\n", stdout)
            
        except Exception as e:
            self._write(f"✗ Failed to reload config: {e}\n", stdout)
            context.last_exit_code = 1

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
        for i, k in enumerate(keys[:-1]):
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
        if value_lower == "true": return True
        if value_lower == "false": return False
        if value_lower == "null": return None
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value
