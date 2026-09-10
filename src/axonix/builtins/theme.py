from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class ThemeCommand(BaseCommand):
    help = "Manage shell themes"
    usage = "theme [list|set|preview|export|import|install|variants] [name|path|url]"
    tags = ["builtin", "ui"]
    examples = [
        "theme                  - Show current theme",
        "theme list             - List available themes",
        "theme set dracula      - Apply Dracula theme",
        "theme preview nord     - Preview Nord theme",
        "theme variants dracula - Show all Dracula variants",
        "theme export mytheme   - Export current colors",
        "theme import ~/t.json  - Import theme from file",
        "theme install <url>    - Download theme from URL",
    ]

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        from axonix.utils.themes import ThemeManager

        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err("theme: shell reference not available\n", stderr)
            return 1
        config = shell.config  # the live config, not a fresh read of the file
        manager = ThemeManager(config)

        if not args:
            self._write(f"Current theme: {config.active_theme}\n", stdout)
            self._write("Use 'theme list' to see available themes\n", stdout)
            return 0
        
        subcommand = args[0].lower()
    
        if subcommand == "list":
            # Include invalid themes to show errors
            themes = manager.list_themes(include_invalid=True)
            validation_errors = manager.get_validation_errors()
            
            self._write("\nAvailable themes:\n\n", stdout)
            for name, info in sorted(themes.items()):
                data = info["data"]
                is_valid = info.get("valid", True)
                theme_type = data.get("type", "dark")
                author = data.get("author", "Unknown")
                display_name = data.get("name", name)
                
                if is_valid:
                    color = config.colors.info
                    self._print_colored([
                        (color, f"  {display_name}"),
                        ("", f" ({theme_type}) - by {author}")
                    ], stdout)
                else:
                    # Show invalid themes with warning
                    self._print_colored([
                        (config.colors.warning, f"  {display_name}"),
                        (config.colors.error, " ⚠ invalid"),
                        ("", f" ({theme_type}) - by {author}")
                    ], stdout)
            
            # Show validation errors if any
            if validation_errors:
                self._write("\n⚠ Theme validation issues:\n", stdout)
                for theme_name, errors in validation_errors.items():
                    self._print_colored([
                        (config.colors.warning, f"  {theme_name}: "),
                        (config.colors.error, "; ".join(errors))
                    ], stdout)
            
            self._write("\n", stdout)
        
        elif subcommand == "set":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <name>")
            
            theme_name = args[1].lower()
            
            if not manager.apply_theme(theme_name, shell):
                self._write_err(f"theme: '{theme_name}' not found\n", stderr)
                return 1
            self._print_colored([
                (config.colors.exit_code_ok, "✓ "),
                ("", f"Theme '{theme_name}' applied")
            ], stdout)
        
        elif subcommand == "preview":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <name>")
            
            theme_name = args[1].lower()
            preview = manager.preview_theme(theme_name)
            
            if preview:
                self._write(f"\n{preview}\n\n", stdout)
                
                # Show color samples
                theme = manager.get_theme(theme_name)
                if theme:
                    colors = theme.get("colors", {})
                    self._write("Sample:\n", stdout)
                    self._print_colored([
                        (colors.get("command", "#ffffff"), "command "),
                        (colors.get("operator", "#ffffff"), "| "),
                        (colors.get("variable", "#ffffff"), "$variable "),
                        (colors.get("string", "#ffffff"), '"string"'),
                        ("", " "),
                        (colors.get("comment", "#ffffff"), "# comment"),
                    ], stdout)
                    self._write("\n\n", stdout)
            else:
                self._write_err(f"theme: '{theme_name}' not found\n", stderr)
                return 1
        
        elif subcommand == "export":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <name>")
            
            name = args[1]
            path = f"{name}.json"
            success = manager.export_theme(name, path)
            
            if not success:
                self._write_err(f"theme: failed to export '{name}'\n", stderr)
                return 1
            self._write(f"Theme exported to {path}\n", stdout)
        
        elif subcommand == "import":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <path>")
            
            import os
            path = os.path.expanduser(args[1])
            name = manager.import_theme(path)
            
            if not name:
                self._write_err(f"theme: failed to import theme from {path}\n", stderr)
                return 1
            self._write(f"Theme '{name}' imported successfully\n", stdout)
            self._write(f"Use 'theme set {name}' to apply it\n", stdout)
        
        elif subcommand == "install":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <url>")
            
            url = args[1]
            self._write(f"Downloading theme from {url}...\n", stdout)
            
            name = manager.install_theme(url)
            
            if not name:
                self._write_err(
                    "theme: failed to install theme "
                    "(make sure the URL points to a valid JSON theme file)\n",
                    stderr,
                )
                return 1
            self._print_colored([
                (config.colors.exit_code_ok, "✓ "),
                ("", f"Theme '{name}' installed")
            ], stdout)
            self._write(f"Use 'theme set {name}' to apply it\n", stdout)
        
        elif subcommand == "variants":
            if len(args) < 2:
                raise ArgumentError(self.name, args, reason="expected <name>")
            
            base_name = args[1].lower()
            variants = manager.get_theme_variants(base_name)
            
            if variants:
                self._write(f"\nVariants of '{base_name}':\n", stdout)
                for v in variants:
                    theme = manager.get_theme(v)
                    if theme:
                        theme_type = theme.get("type", "dark")
                        self._print_colored([
                            (config.colors.info, f"  {v}"),
                            ("", f" ({theme_type})")
                        ], stdout)
                self._write("\n", stdout)
            else:
                self._write_err(f"theme: no variants found for '{base_name}'\n", stderr)
                return 1

        else:
            raise ArgumentError(self.name, subcommand, reason="unknown subcommand")
        return 0

    def get_completer(self):
        """Return the ThemeCompleter."""
        from axonix.ui.completers.theme import ThemeCompleter
        return ThemeCompleter()
