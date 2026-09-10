from zem.builtins.base import BaseCommand


class FalseCommand(BaseCommand):
    help = "Do nothing, unsuccessfully"
    usage = "false"

    def execute(self, args, context, stdin=None, stdout=None) -> int:
        return 1
