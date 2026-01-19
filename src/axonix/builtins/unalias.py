from axonix.builtins.base import BaseCommand

class UnaliasCommand(BaseCommand):
    name = "unalias"
    help = "Remove an alias"
    usage = "unalias <name>"

    def execute(self, args: list[str], context, stdin=None, stdout=None):
        if not args:
            stdout.write("unalias: usage: unalias <name>\n")
            return
            
        for name in args:
            if name in context.aliases:
                del context.aliases[name]
            else:
                stdout.write(f"unalias: {name}: not found\n")