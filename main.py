import sys
from pydantic import ValidationError

def main():
    try:
        from src.core.shell import Shell
        shell = Shell()
        shell.run()
    except ValidationError as e:
        print(f"\033[91mConfiguration Error:\033[0m")
        for error in e.errors():
            loc = ".".join(str(x) for x in error['loc'])
            print(f"  - {loc}: {error['msg']}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to start shell: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
