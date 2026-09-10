from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand

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
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText

        from axonix.config.settings import AppConfig
        from axonix.utils.themes import ThemeManager
        
        config = AppConfig()
        manager = ThemeManager(config)
        
        # Get shell reference from context
        shell = getattr(context, '_shell', None)
        
        if not args:
            # Show current theme info
            active = getattr(config, 'active_theme', 'default')
            self._write(f"Current theme: {active}\n", stdout)
            self._write("Use 'theme list' to see available themes\n", stdout)
            return
        
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
                    print_formatted_text(FormattedText([
                        (color, f"  {display_name}"),
                        ("", f" ({theme_type}) - by {author}")
                    ]))
                else:
                    # Show invalid themes with warning
                    print_formatted_text(FormattedText([
                        (config.colors.warning, f"  {display_name}"),
                        (config.colors.error, " ⚠ invalid"),
                        ("", f" ({theme_type}) - by {author}")
                    ]))
            
            # Show validation errors if any
            if validation_errors:
                self._write("\n⚠ Theme validation issues:\n", stdout)
                for theme_name, errors in validation_errors.items():
                    print_formatted_text(FormattedText([
                        (config.colors.warning, f"  {theme_name}: "),
                        (config.colors.error, "; ".join(errors))
                    ]))
            
            self._write("\n", stdout)
        
        elif subcommand == "set":
            if len(args) < 2:
                self._write("Usage: theme set <name>\n", stdout)
                return
            
            theme_name = args[1].lower()
            
            if shell:
                success = manager.apply_theme(theme_name, shell)
                if success:
                    print_formatted_text(FormattedText([
                        (config.colors.exit_code_ok, "✓ "),
                        ("", f"Theme '{theme_name}' applied successfully!")
                    ]))
                    self._write("\n", stdout)
                else:
                    print_formatted_text(FormattedText([
                        (config.colors.error, "✗ "),
                        ("", f"Theme '{theme_name}' not found")
                    ]))
                    self._write("\n", stdout)
            else:
                self._write("Error: Cannot apply theme (shell reference not found)\n", stdout)
        
        elif subcommand == "preview":
            if len(args) < 2:
                self._write("Usage: theme preview <name>\n", stdout)
                return
            
            theme_name = args[1].lower()
            preview = manager.preview_theme(theme_name)
            
            if preview:
                self._write(f"\n{preview}\n\n", stdout)
                
                # Show color samples
                theme = manager.get_theme(theme_name)
                if theme:
                    colors = theme.get("colors", {})
                    self._write("Sample:\n", stdout)
                    print_formatted_text(FormattedText([
                        (colors.get("command", "#ffffff"), "command "),
                        (colors.get("operator", "#ffffff"), "| "),
                        (colors.get("variable", "#ffffff"), "$variable "),
                        (colors.get("string", "#ffffff"), '"string"'),
                        ("", " "),
                        (colors.get("comment", "#ffffff"), "# comment"),
                    ]))
                    self._write("\n\n", stdout)
            else:
                self._write(f"Theme '{theme_name}' not found\n", stdout)
        
        elif subcommand == "export":
            if len(args) < 2:
                self._write("Usage: theme export <name>\n", stdout)
                return
            
            name = args[1]
            path = f"{name}.json"
            success = manager.export_theme(name, path)
            
            if success:
                self._write(f"Theme exported to {path}\n", stdout)
            else:
                self._write("Failed to export theme\n", stdout)
        
        elif subcommand == "import":
            if len(args) < 2:
                self._write("Usage: theme import <path>\n", stdout)
                return
            
            import os
            path = os.path.expanduser(args[1])
            name = manager.import_theme(path)
            
            if name:
                self._write(f"Theme '{name}' imported successfully\n", stdout)
                self._write(f"Use 'theme set {name}' to apply it\n", stdout)
            else:
                self._write(f"Failed to import theme from {path}\n", stdout)
        
        elif subcommand == "install":
            if len(args) < 2:
                self._write("Usage: theme install <url>\n", stdout)
                self._write("Example: theme install https://example.com/mytheme.json\n", stdout)
                return
            
            url = args[1]
            self._write(f"Downloading theme from {url}...\n", stdout)
            
            name = manager.install_theme(url)
            
            if name:
                print_formatted_text(FormattedText([
                    (config.colors.exit_code_ok, "✓ "),
                    ("", f"Theme '{name}' installed successfully!")
                ]))
                self._write(f"\nUse 'theme set {name}' to apply it\n", stdout)
            else:
                print_formatted_text(FormattedText([
                    (config.colors.error, "✗ "),
                    ("", "Failed to install theme")
                ]))
                self._write("\nMake sure the URL points to a valid JSON theme file\n", stdout)
        
        elif subcommand == "variants":
            if len(args) < 2:
                self._write("Usage: theme variants <name>\n", stdout)
                return
            
            base_name = args[1].lower()
            variants = manager.get_theme_variants(base_name)
            
            if variants:
                self._write(f"\nVariants of '{base_name}':\n", stdout)
                for v in variants:
                    theme = manager.get_theme(v)
                    if theme:
                        theme_type = theme.get("type", "dark")
                        print_formatted_text(FormattedText([
                            (config.colors.info, f"  {v}"),
                            ("", f" ({theme_type})")
                        ]))
                self._write("\n", stdout)
            else:
                self._write(f"No variants found for '{base_name}'\n", stdout)
        
        else:
            self._write(f"Unknown subcommand: {subcommand}\n", stdout)
            self._write(f"Usage: {self.usage}\n", stdout)

    def get_completer(self):
        """Return the ThemeCompleter."""
        from axonix.config.settings import AppConfig
        from axonix.ui.completers.theme import ThemeCompleter
        return ThemeCompleter(AppConfig())
