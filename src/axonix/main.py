import sys
from pydantic import ValidationError


def main():
    try:
        from axonix.core.shell import Shell
        shell = Shell()
        shell.run()
    except ValidationError as e:
        from prompt_toolkit import print_formatted_text, HTML
        from axonix.utils.colors import error_tag
        from axonix.config.settings import AppConfig
        
        config = AppConfig()
        print_formatted_text(HTML(f"{error_tag(config)} Configuration Error:"))
        for error in e.errors():
            loc = ".".join(str(x) for x in error['loc'])
            print_formatted_text(HTML(f"  <ansiyellow>-</ansiyellow> <ansicyan>{loc}</ansicyan>: {error['msg']}"))
        sys.exit(1)
    except Exception as e:
        from prompt_toolkit import print_formatted_text, HTML
        from axonix.utils.colors import error_tag
        from axonix.config.settings import AppConfig
        
        config = AppConfig()
        print_formatted_text(HTML(f"{error_tag(config)} Failed to start shell: {e}"))
        sys.exit(1)

if __name__ == "__main__":
    main()
