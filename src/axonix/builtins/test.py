from axonix.builtins._test_expr import ExprSyntaxError, evaluate
from axonix.builtins.base import BaseCommand


class TestExprCommand(BaseCommand):
    name = "test"
    help = "Evaluate a conditional expression"
    usage = "test EXPRESSION | [ EXPRESSION ]"
    examples = [
        "test -d /tmp && echo dir      - File tests: -e -f -d -L -r -w -x -s",
        "[ \"$X\" = abc ]                - String tests: = != < > -z -n",
        "[ 3 -gt 2 ]                    - Integer tests: -eq -ne -lt -le -gt -ge",
        "[ ! -e f -a -d d ]             - Negation and -a / -o, ( ) grouping",
    ]

    def _evaluate(self, args: list[str], stderr) -> int:
        try:
            return 0 if evaluate(args) else 1
        except ExprSyntaxError as e:
            self._write_err(f"{self.name}: {e}\n", stderr)
            return 2

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        return self._evaluate(args, stderr)


class BracketCommand(TestExprCommand):
    name = "["
    help = "Evaluate a conditional expression (closing ] required)"
    usage = "[ EXPRESSION ]"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if not args or args[-1] != "]":
            self._write_err("[: missing ']'\n", stderr)
            return 2
        return self._evaluate(args[:-1], stderr)
