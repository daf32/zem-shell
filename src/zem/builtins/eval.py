from zem.builtins.base import BaseCommand


class EvalCommand(BaseCommand):
    help = "Join the arguments into one line and run it in this shell"
    usage = "eval [ARG...]"
    examples = [
        "eval echo '$HOME'     - Expand and run",
        "set CMD 'ls -la'; eval $CMD",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if not args:
            return 0
        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err("eval: shell reference not available\n", stderr)
            return 1
        shell._execute_line(" ".join(args), add_to_history=False)
        return context.last_exit_code
