"""Evaluator for `test` / `[` expressions (POSIX subset, pure function)."""

from __future__ import annotations

import os


class ExprSyntaxError(ValueError):
    """Malformed expression; `test` maps it to exit code 2."""


_UNARY_FILE = {
    "-e": os.path.exists,
    "-f": os.path.isfile,
    "-d": os.path.isdir,
    "-L": os.path.islink,
    "-h": os.path.islink,
    "-r": lambda p: os.access(p, os.R_OK),
    "-w": lambda p: os.access(p, os.W_OK),
    "-x": lambda p: os.access(p, os.X_OK),
    "-s": lambda p: os.path.exists(p) and os.path.getsize(p) > 0,
}
_UNARY_STRING = {
    "-z": lambda s: s == "",
    "-n": lambda s: s != "",
}
_BINARY_STRING = {
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
}
_BINARY_INT = {
    "-eq": lambda a, b: a == b,
    "-ne": lambda a, b: a != b,
    "-lt": lambda a, b: a < b,
    "-le": lambda a, b: a <= b,
    "-gt": lambda a, b: a > b,
    "-ge": lambda a, b: a >= b,
}


def _to_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ExprSyntaxError(f"integer expression expected: {value!r}") from None


class _Parser:
    """Recursive descent: or -> and -> not -> primary."""

    def __init__(self, args: list[str]):
        self.args = args
        self.pos = 0

    def peek(self) -> str | None:
        return self.args[self.pos] if self.pos < len(self.args) else None

    def take(self) -> str:
        if self.pos >= len(self.args):
            raise ExprSyntaxError("argument expected")
        value = self.args[self.pos]
        self.pos += 1
        return value

    def parse(self) -> bool:
        if not self.args:
            return False
        result = self.expr_or()
        if self.pos != len(self.args):
            raise ExprSyntaxError(f"unexpected argument: {self.args[self.pos]!r}")
        return result

    def expr_or(self) -> bool:
        left = self.expr_and()
        while self.peek() == "-o":
            self.take()
            right = self.expr_and()
            left = left or right
        return left

    def expr_and(self) -> bool:
        left = self.expr_not()
        while self.peek() == "-a":
            self.take()
            right = self.expr_not()
            left = left and right
        return left

    def expr_not(self) -> bool:
        if self.peek() == "!":
            self.take()
            return not self.expr_not()
        return self.primary()

    def primary(self) -> bool:
        tok = self.take()
        if tok == "(":
            inner = self.expr_or()
            if self.take() != ")":
                raise ExprSyntaxError("missing ')'")
            return inner

        nxt = self.peek()
        # Binary operators take precedence over a leading unary flag so
        # that `-n = -n` compares strings, like coreutils does.
        if nxt in _BINARY_STRING or nxt in _BINARY_INT:
            op = self.take()
            rhs = self.take()
            if op in _BINARY_INT:
                return _BINARY_INT[op](_to_int(tok), _to_int(rhs))
            return _BINARY_STRING[op](tok, rhs)

        if tok in _UNARY_FILE:
            return _UNARY_FILE[tok](self.take())
        if tok in _UNARY_STRING:
            return _UNARY_STRING[tok](self.take())
        if tok.startswith("-") and len(tok) > 1 and nxt is not None:
            raise ExprSyntaxError(f"unknown operator: {tok}")
        # A lone string is true when non-empty.
        return tok != ""


def evaluate(args: list[str]) -> bool:
    """Evaluate a `test` expression. Raises :class:`ExprSyntaxError`."""
    return _Parser(list(args)).parse()
