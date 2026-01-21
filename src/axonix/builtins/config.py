import json
import os
from typing import Any, List, Optional
from axonix.builtins.base import BaseCommand
from axonix.core.context import ExecutionContext
from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

class ConfigCompleter(BaseArgCompleter):
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
        # parts example: ['config', 'set', 'key']
        
        # 1. Subcommands completion (list, get, set)
        # parts: ['config', ''] -> len 2
        if len(parts) == 2:
            current_subcmd = parts[1]
            for cmd in ["list", "get", "set"]:
                if cmd.startswith(current_subcmd):
                    yield Completion(cmd, start_position=-len(current_subcmd))
            return

        # 2. Key completion
        # parts: ['config', 'set', 'key_prefix'] -> len 3
        if len(parts) >= 3:
            subcmd = parts[1]
            if subcmd in ["get", "set"]:
                # Only complete key if it's the 3rd argument (index 2)
                # For 'set', we have a value at index 3, we usually don't complete values unless enum.
                if len(parts) == 3:
                     # Suggest keys
                    all_keys = self._get_keys(self.config_data)
                    current_input = parts[2]
                    
                    for key in all_keys:
                        if key.lower().startswith(current_input.lower()):
                            yield Completion(key, start_position=-len(current_input))

class ConfigCommand(BaseCommand):
    name = "config"
    help = "Manage shell configuration"
    usage = "config [list|get <key>|set <key> <value>]"
    tags = ["builtin", "core"]

    def get_completer(self):
        # We need to load fresh config data for completion
        from axonix.config.settings import CONFIG_PATH
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            return ConfigCompleter(data)
        except:
            return None

    def execute(self, args: list[str], context: ExecutionContext, stdin=None, stdout=None):
        if not args:
            self._write(f"Usage: {self.usage}\n", stdout)
            return

        command = args[0]
        
        from axonix.config.settings import CONFIG_PATH
        
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
                
        elif command == "set":
            if len(args) < 3:
                self._write("Usage: config set <key> <value>\n", stdout)
                return
            key = args[1]
            value_str = " ".join(args[2:]) # Allow values with spaces? Or strict?
            # Better to take just one arg usually, but CLI args are split by space.
            # Let's join the rest as value strings usually don't need executing.
            
            # Type inference
            value = self._infer_type(value_str)
            
            if self._set_value(data, key, value):
                # Save to disk
                with open(CONFIG_PATH, "w") as f:
                    json.dump(data, f, indent=4)
                
                self._write(f"✅ Set '{key}' to '{value}'\n", stdout)
                
                # Attempt Hot Reload (Partial)
                # We can update context._shell.config directly?
                # It's a Pydantic model. We can try to reload attributes.
                if hasattr(context, '_shell'):
                    # Simplest way: re-instantiate AppConfig if possible or patch dict
                    # Since Pydantic models are mostly immutable or validated...
                    # Let's just warn for restart for now, or patch the specific value if we can reach it.
                    self._write("ℹ️  Changes saved. Some settings may require a shell restart.\n", stdout)
                    
                    # Update active theme if colors changed?
                    if key.startswith("colors."):
                        from axonix.utils.themes import ThemeManager
                        ThemeManager.apply_theme(context._shell, context._shell.config.active_theme)

            else:
                self._write(f"❌ Failed to set '{key}'. Check if parent keys exist.\n", stdout)

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
