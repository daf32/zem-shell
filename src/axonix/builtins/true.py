from axonix.builtins.base import BaseCommand


class TrueCommand(BaseCommand):
    help = "Do nothing, successfully"
    usage = "true"

    def execute(self, args, context, stdin=None, stdout=None) -> int:
        return 0


class ColonCommand(TrueCommand):
    name = ":"
    help = "Null command (same as true)"
    usage = ":"
