from axonix.builtins.base import BaseCommand


class AliasCommand(BaseCommand):
    name = "alias"
    help = "Create or list aliases"
    usage = "alias [name[=value] ... ]"
    
    def execute(self, args: list[str], context, stdin=None, stdout=None):
        if not args:
            for name, value in sorted(context.aliases.items()):
                self._write(f"alias {name}='{value}'\n", stdout)
            return
        for arg in args:
            if "=" in arg:
                name, value = arg.split("=", 1)
                context.aliases[name.strip()] = value.strip("'\"")
            else:
                if arg in context.aliases:
                    self._write(f"alias {arg}='{context.aliases[arg]}'\n", stdout)
                else:
                    self._write(f"axonix: alias: {arg}: not found\n", stdout)