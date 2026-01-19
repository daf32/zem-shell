from axonix.builtins.base import BaseCommand


class AliasCommand(BaseCommand):
    name = "alias"
    help = "Create or list aliases"
    usage = "alias [name[=value] ... ]"
    
    def execute(self, args: list[str], context, stdin=None, stdout=None):
        if not args:
            for name, value in sorted(context.aliases.items()):
                stdout.write(f"alias {name}='{value}'\n")
            return
        for arg in args:
            if "=" in arg:
                name, value = arg.split("=", 1)
                context.aliases[name.strip()] = value.strip("'\"")
            else:
                if arg in context.aliases:
                    stdout.write(f"alias {arg}='{context.aliases[arg]}'\n")
                else:
                    stdout.write(f"axonix: alias: {arg}: not found\n")