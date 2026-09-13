import os
import re
from typing import TYPE_CHECKING, Callable, Iterator, Optional

from zem.core.scan import (
    COMMENT,
    DOUBLE,
    NORMAL,
    SINGLE,
    SUBST,
    escapes_next,
    needs_continuation,
    scan,
    split_words,
)
from zem.errors.parser_error import ParseError, UnclosedQuoteError

if TYPE_CHECKING:
    from zem.config.settings import AppConfig

#: A logical unit before tokenization: its text, the operator that follows
#: it (`&&`, `||`, `;` or None) and whether a `&` ended it.
Segment = tuple[str, Optional[str], bool]


class Parser:
    NORMAL, SINGLE, DOUBLE, SUBST, COMMENT = NORMAL, SINGLE, DOUBLE, SUBST, COMMENT

    #: Descriptors an ``N>&M`` duplication may name; the executor wires up
    #: stdout and stderr only.
    DUP_FDS = ("1", "2")

    #: Characters that name a special parameter after ``$``.
    SPECIAL_VARS = "?$!#@*"

    def __init__(
        self,
        text: str,
        variables: dict,
        aliases: dict,
        config: "AppConfig",
        substitutor: Optional[Callable[[str], str]] = None,
    ):
        """
        ``substitutor`` runs the text inside ``$(...)`` and returns its
        output; without one, command substitution is a parse error.
        """
        self.text = text
        self.variables = variables
        self.aliases = aliases
        self.config = config
        self.substitutor = substitutor

    # -- expansion helpers ----------------------------------------------------

    def _literal(self, value: str, in_double: bool = False) -> str:
        """Escape expanded text so later passes read it back verbatim.

        Expanded values (variables, command output) are spliced into the
        raw token buffer, which `_remove_quotes` re-scans; a quote or
        backslash in the value would otherwise be interpreted as syntax.
        Inside double quotes only the characters a backslash can escape
        there need protecting -- escaping a `'` would keep the backslash.
        """
        esc = self.config.operators.escape
        if in_double:
            specials = (esc, self.config.operators.double_quote, self.config.operators.variable)
        else:
            specials = (esc, self.config.operators.quote, self.config.operators.double_quote)
        for ch in specials:
            value = value.replace(ch, esc + ch)
        return value

    def _variable_value(self, name: str) -> str:
        """The value ``$name`` expands to, special parameters included."""
        if name == "$":
            return str(os.getpid())
        if name == "0":
            return "zem"
        if name == "#":
            return "0"  # scripts take no positional parameters yet
        if name in ("@", "*"):
            return ""
        return str(self.variables.get(name, ""))

    def _find_closing_paren(self, text: str, start: int) -> int:
        """Index of the ``)`` matching the ``(`` at ``start`` (quote-aware)."""
        depth = 0
        state = NORMAL
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == self.config.operators.escape and escapes_next(text, i, state):
                escaped = True
            elif state == NORMAL:
                if ch == self.config.operators.quote:
                    state = SINGLE
                elif ch == self.config.operators.double_quote:
                    state = DOUBLE
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        return i
            elif state == SINGLE and ch == self.config.operators.quote:
                state = NORMAL
            elif state == DOUBLE and ch == self.config.operators.double_quote:
                state = NORMAL
        raise ParseError("Unclosed command substitution '$('")

    def _substitute(self, text: str, open_idx: int) -> tuple[str, int]:
        """Run the ``$( ... )`` starting at ``open_idx`` (the ``(``).

        Returns ``(output, index_after_closing_paren)``. Trailing newlines
        are stripped like in POSIX shells.
        """
        if self.substitutor is None:
            raise ParseError("Command substitution is not available here")
        close = self._find_closing_paren(text, open_idx)
        output = self.substitutor(text[open_idx + 1:close])
        return output.rstrip("\n"), close + 1

    def _walk(self, text: str):
        """Yield ``(char, escaped, state)``; see :func:`zem.core.scan.scan`."""
        chars, state, _ = scan(text, self.config.operators)
        yield from chars
        if state != NORMAL:
            raise UnclosedQuoteError()

    @staticmethod
    def needs_continuation(text: str, config: "AppConfig") -> bool:
        """True when ``text`` is an incomplete line (see :mod:`zem.core.scan`)."""
        return needs_continuation(text, config.operators)

    # -- aliases -------------------------------------------------------------

    def _expand_alias_text(self, segment: str, chain: frozenset) -> Optional[tuple[str, frozenset]]:
        """Substitute aliases in command position of every stage of ``segment``.

        Like bash, an alias is replaced by its definition *as text*, and the
        result is parsed again: a body such as ``git log | head`` or
        ``git pull && uv sync`` keeps its operators. Returns ``(new_text,
        names)``, or ``None`` when no stage starts with an alias that is
        not already being expanded (``chain``).
        """
        stages = self._split_by_pipe(segment)
        used: set[str] = set()
        out: list[str] = []
        for stage in stages:
            expanded = self._expand_alias_stage(stage, chain)
            if expanded is None:
                out.append(stage)
            else:
                out.append(expanded[0])
                used.add(expanded[1])
        if not used:
            return None
        return self.config.operators.pipe.join(out), frozenset(used)

    def _expand_alias_stage(self, stage: str, chain: frozenset) -> Optional[tuple[str, str]]:
        """One pipeline stage: ``(replacement_text, alias_name)`` or ``None``.

        ``$1..$N`` in the body consume that many following words (raw,
        quotes intact); the rest of the stage follows the expansion
        untouched. A quoted or escaped first word bypasses aliases.
        """
        words = split_words(stage, self.config.operators)
        if not words:
            return None
        head = words[0]
        if head.is_redirect or head.text != head.value:
            return None  # `'ls'` and `\ls` bypass aliases, like in bash
        name = head.value
        if name not in self.aliases or name in chain:
            return None

        body = self.aliases[name]
        indices = sorted({int(p) for p in re.findall(r"\$(\d+)", body)}, reverse=True)
        if not indices:
            return body + stage[head.end:], name

        max_index = indices[0]
        for i in indices:
            value = words[i].text if i < len(words) else ""
            body = body.replace(f"${i}", value)
        rest = stage[words[max_index].end:] if max_index < len(words) else ""
        return body + rest, name

    # -- splitting -----------------------------------------------------------

    def _split_by_pipe(self, text: str) -> list[str]:
        """Split by pipe operator, but not || (logical OR)."""
        segments = []
        current = []

        chars = list(self._walk(text))
        i = 0
        while i < len(chars):
            ch, escaped, state = chars[i]

            if not escaped and state == NORMAL and ch == self.config.operators.pipe:
                # Check if this is part of || operator
                if i + 1 < len(chars):
                    next_ch, next_escaped, next_state = chars[i + 1]
                    if next_ch == "|" and not next_escaped and next_state == NORMAL:
                        # This is ||, not a pipe - add both chars and continue
                        current.append(ch)
                        current.append(next_ch)
                        i += 2
                        continue

                # This is a pipe operator
                segments.append("".join(current))
                current = []
                i += 1
                continue

            current.append(ch)
            i += 1

        segments.append("".join(current))
        if text.strip().endswith(self.config.operators.pipe):
            raise ParseError("Empty command after pipe")
        return segments

    def _split_logic(self, text: str) -> list[Segment]:
        """Split text into logical units at ``&&``, ``||``, ``;`` and ``&``.

        Comments are dropped here, before anything else looks at the text,
        so a ``|`` or ``;`` inside one can never start a command. A single
        ``&`` ends a unit like ``;`` does and marks it for the background;
        the ``&`` of ``&>``/``>&`` is a redirection, not a separator.
        """
        ops = self.config.operators
        segments: list[Segment] = []
        current: list[str] = []

        i = 0
        chars = list(self._walk(text))
        while i < len(chars):
            ch, escaped, state = chars[i]

            if state == COMMENT:
                if ch == "\n":
                    current.append(ch)  # the line ends with the comment
                i += 1
                continue

            if not escaped and state == NORMAL:
                nxt = chars[i + 1] if i + 1 < len(chars) else None
                prev = chars[i - 1] if i > 0 else None
                if ch == ops.background:
                    if nxt and nxt[0] == ops.background and not nxt[1] and nxt[2] == NORMAL:
                        segments.append(("".join(current), "&&", False))
                        current = []
                        i += 2
                        continue
                    is_redirect = (nxt is not None and nxt[0] == ops.redirect_output) or (
                        prev is not None and prev[0] == ops.redirect_output and prev[2] == NORMAL
                    )
                    if not is_redirect:
                        segments.append(("".join(current), ";", True))
                        current = []
                        i += 1
                        continue
                # `||` -- but a single `|` is a pipe, left for `_split_by_pipe`
                if ch == ops.pipe and nxt and nxt[0] == ops.pipe and not nxt[1] \
                        and nxt[2] == NORMAL:
                    segments.append(("".join(current), "||", False))
                    current = []
                    i += 2
                    continue
                if ch == ops.semicolon:
                    segments.append(("".join(current), ";", False))
                    current = []
                    i += 1
                    continue

            current.append(ch)
            i += 1

        segments.append(("".join(current), None, False))
        return segments

    # -- tokens --------------------------------------------------------------

    def _get_var_name(self, text: str, start: int) -> tuple[str, int]:
        if start >= len(text):
            return "", start
        if text[start] == self.config.operators.variable_start:
            end = text.find(self.config.operators.variable_end, start)
            if end == -1:
                return text[start+1:], len(text)
            return text[start+1:end], end + 1
        if text[start] in self.SPECIAL_VARS or text[start].isdigit():
            return text[start], start + 1
        match = re.search(r'^(\w+)', text[start:])
        if match:
            name = match.group(1)
            return name, start + len(name)
        return "", start

    def _tokenize(self, text: str) -> list[str]:
        tokens = []
        current = []
        state = NORMAL
        escaped = False
        in_token = False

        i = 0
        while i < len(text):
            ch = text[i]

            if escaped:
                # Keep the backslash: quotes stay in the token until
                # `_remove_quotes`, which must see the escape to know this
                # character is literal (otherwise `a\'b` would read as a
                # quote opening).
                current.append(self.config.operators.escape)
                current.append(ch)
                escaped = False
                i += 1
                continue
            if ch == self.config.operators.escape and escapes_next(text, i, state):
                escaped = True
                in_token = True
                i += 1
                continue

            if state == NORMAL:
                if ch.isspace():
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                elif ch == self.config.operators.comment and not in_token:
                    break  # a comment runs to the end of the line
                elif ch == self.config.operators.quote:
                    state, in_token = SINGLE, True
                    current.append(ch)
                elif ch == self.config.operators.double_quote:
                    state, in_token = DOUBLE, True
                    current.append(ch)
                elif ch == self.config.operators.variable:
                    if text[i + 1:i + 2] == "(":
                        output, next_i = self._substitute(text, i + 1)
                        # Word-split the output (unquoted context).
                        pieces = output.split()
                        for idx, piece in enumerate(pieces):
                            if idx > 0:
                                tokens.append("".join(current))
                                current = []
                            current.append(self._literal(piece))
                            in_token = True
                        i = next_i - 1
                    else:
                        name, next_i = self._get_var_name(text, i + 1)
                        value = self._variable_value(name)
                        current.append(self._literal(value))
                        # An empty unquoted expansion vanishes (`ls $UNSET`
                        # runs `ls`, not `ls ''`); `"$UNSET"` still yields
                        # an empty argument through the DOUBLE branch.
                        i, in_token = next_i - 1, in_token or bool(value)
                elif ch in (
                    self.config.operators.redirect_output,
                    self.config.operators.redirect_input,
                ):
                    # `2>` / `1>`: a bare fd number glued to `>` is an fd
                    # prefix (bash: `echo 2>x` redirects, `echo 2 >x` prints).
                    fd_prefix = ""
                    if (
                        ch == self.config.operators.redirect_output
                        and in_token
                        and "".join(current) in ("1", "2")
                    ):
                        fd_prefix = "".join(current)
                        current, in_token = [], False
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False

                    op = ch
                    if ch == self.config.operators.redirect_output:
                        rem = self.config.operators.redirect_append[1:]
                        if text[i + 1:i + 1 + len(rem)] == rem:
                            op = self.config.operators.redirect_append
                            i += len(rem)
                        elif text[i + 1:i + 2] == self.config.operators.background:
                            # `>&M` / `N>&M`: duplicate a descriptor.
                            op, i = self._read_fd_dup(text, i, fd_prefix or "1")
                            fd_prefix = ""
                    if fd_prefix == "2":
                        op = "2" + op
                    tokens.append(op)
                elif ch == self.config.operators.background and \
                        text[i + 1:i + 2] == self.config.operators.redirect_output:
                    # `&>` / `&>>`: redirect both stdout and stderr. A lone
                    # `&` never gets here: `_split_logic` consumed it.
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                    if text[i + 1:i + 3] == self.config.operators.redirect_append:
                        tokens.append("&>>")
                        i += 2
                    else:
                        tokens.append("&>")
                        i += 1
                else:
                    current.append(ch)
                    in_token = True
            elif state == SINGLE:
                if ch == self.config.operators.quote:
                    state = NORMAL
                    current.append(ch)
                else:
                    current.append(ch)
            elif state == DOUBLE:
                if ch == self.config.operators.double_quote:
                    state = NORMAL
                    current.append(ch)
                elif ch == self.config.operators.variable:
                    if text[i + 1:i + 2] == "(":
                        output, next_i = self._substitute(text, i + 1)
                        current.append(self._literal(output, in_double=True))  # verbatim
                        i = next_i - 1
                    else:
                        name, next_i = self._get_var_name(text, i + 1)
                        current.append(self._literal(self._variable_value(name), in_double=True))
                        i = next_i - 1
                else:
                    current.append(ch)

            i += 1

        if in_token:
            tokens.append("".join(current))
        return tokens

    def _read_fd_dup(self, text: str, i: int, src_fd: str) -> tuple[str, int]:
        """Read the ``&M`` of an ``N>&M`` descriptor duplication.

        ``text[i]`` is the ``>`` and ``text[i + 1]`` the ``&``; returns the
        canonical ``"N>&M"`` token and the index of its last character.
        Only stdout and stderr are wired up, so any other descriptor is a
        parse error — better than the file named ``&`` that ``>&2`` used
        to create.
        """
        j = i + 2
        while j < len(text) and text[j].isdigit():
            j += 1
        dst_fd = text[i + 2:j]
        rest = text[j:j + 1]
        if not dst_fd:
            raise ParseError(f"Missing file descriptor after '{src_fd}>&'")
        if dst_fd not in self.DUP_FDS:
            raise ParseError(
                f"Unsupported file descriptor '{dst_fd}' in '{src_fd}>&{dst_fd}': "
                "only 1 (stdout) and 2 (stderr) can be duplicated"
            )
        ops = self.config.operators
        delimiters = (
            ops.background,
            ops.pipe,
            ops.semicolon,
            ops.comment,
            ops.redirect_output,
            ops.redirect_input,
        )
        if rest and not rest.isspace() and rest not in delimiters:
            raise ParseError(f"Ambiguous redirect: '{src_fd}>&{dst_fd}{rest}'")
        return f"{src_fd}>&{dst_fd}", j - 1

    def _extract_redirections(self, tokens: list[str]) -> tuple[list[str], dict]:
        """Split tokens into command words and a redirection spec.

        The spec has keys ``stdin_file``, ``stdout_file``, ``append``,
        ``stderr_file``, ``stderr_append``, ``stderr_to_stdout``,
        ``stdout_to_stderr`` and ``background`` (always False here; the
        caller knows whether the unit ended with ``&``).
        """
        out = self.config.operators.redirect_output
        app = self.config.operators.redirect_append
        cmd_tokens: list[str] = []
        spec: dict = {
            "stdin_file": None,
            "stdout_file": None,
            "append": False,
            "stderr_file": None,
            "stderr_append": False,
            "stderr_to_stdout": False,
            "stdout_to_stderr": False,
            "background": False,
        }

        def target(i: int, op: str) -> str:
            if i + 1 >= len(tokens):
                raise ParseError(f"Missing target after '{op}'")
            return tokens[i + 1]

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in (out, app):
                spec["stdout_file"] = target(i, token)
                spec["append"] = token == app
                i += 2
            elif token in ("2" + out, "2" + app):
                spec["stderr_file"] = target(i, token)
                spec["stderr_append"] = token == "2" + app
                i += 2
            elif token in ("&>", "&>>"):
                spec["stdout_file"] = target(i, token)
                spec["append"] = token == "&>>"
                spec["stderr_to_stdout"] = True
                i += 2
            elif token in ("1>&1", "2>&2"):
                # Duplicating a descriptor onto itself: nothing to wire up.
                i += 1
            elif token == "2>&1":
                spec["stderr_to_stdout"] = True
                spec["stdout_to_stderr"] = False
                i += 1
            elif token == "1>&2":
                spec["stdout_to_stderr"] = True
                spec["stderr_to_stdout"] = False
                i += 1
            elif token == self.config.operators.redirect_input:
                spec["stdin_file"] = target(i, token)
                i += 2
            else:
                cmd_tokens.append(token)
                i += 1
        return cmd_tokens, spec

    def _remove_quotes(self, text: str) -> str:
        """Remove quotes and the escapes they imply from a raw token.

        A backslash outside quotes hides the next character; inside double
        quotes it does so only before the few characters it can escape
        there, and stays put otherwise (`"a\\nb"` keeps its backslash).
        """
        if not text:
            return text

        result = []
        state = NORMAL
        i = 0

        while i < len(text):
            ch = text[i]
            if ch == self.config.operators.escape and escapes_next(text, i, state):
                if i + 1 < len(text):
                    result.append(text[i + 1])
                i += 2
                continue

            if state == NORMAL:
                if ch == self.config.operators.quote:
                    state = SINGLE
                elif ch == self.config.operators.double_quote:
                    state = DOUBLE
                else:
                    result.append(ch)
            elif state == SINGLE:
                if ch == self.config.operators.quote:
                    state = NORMAL
                else:
                    result.append(ch)
            elif state == DOUBLE:
                if ch == self.config.operators.double_quote:
                    state = NORMAL
                else:
                    result.append(ch)
            i += 1

        return "".join(result)

    def _expand_tilde(self, token: str) -> str | None:
        """Expand a leading unquoted ``~`` / ``~user`` in a raw token.

        Returns the expanded (and unquoted) word, or ``None`` if the token
        doesn't start with a tilde. Only the prefix up to the first ``/``
        is expanded; the rest of the word is unquoted as usual.
        """
        if not token.startswith("~"):
            return None
        head, sep, rest = token.partition("/")
        expanded = os.path.expanduser(head)
        if expanded == head:  # unknown user: leave the word alone
            return None
        return expanded + sep + self._remove_quotes(rest)

    def _expand_word(self, token: str) -> str:
        """Unquote a single word, expanding a leading tilde."""
        return self._expand_tilde(token) or self._remove_quotes(token)

    def _expand_words(self, tokens: list[str]) -> list[str]:
        """Unquote words, expanding tildes and globs."""
        import glob

        expanded_tokens = []

        for token in tokens:
            tilde = self._expand_tilde(token)
            if tilde is not None:
                token, remove = tilde, False
            else:
                remove = True
            # Check if token contains unquoted wildcards
            # We need to scan the token similar to _tokenize or _remove_quotes
            # but detecting if *?[ are unquoted

            has_glob = False
            state = NORMAL
            escaped = False

            # Simple heuristic first: if no globs chars, skip expensive parse
            if not any(c in token for c in "*?[]"):
                expanded_tokens.append(self._remove_quotes(token) if remove else token)
                continue

            # Verify if wildcards are unquoted
            for ch in token:
                if escaped:
                    escaped = False
                    continue
                if ch == self.config.operators.escape and state != SINGLE:
                    escaped = True
                    continue

                if state == NORMAL:
                    if ch == self.config.operators.quote:
                        state = SINGLE
                    elif ch == self.config.operators.double_quote:
                        state = DOUBLE
                    elif ch in "*?[]":
                        has_glob = True
                        break
                elif state == SINGLE:
                    if ch == self.config.operators.quote:
                        state = NORMAL
                elif state == DOUBLE:
                    if ch == self.config.operators.double_quote:
                        state = NORMAL

            if has_glob:
                pattern = self._remove_quotes(token) if remove else token
                matches = glob.glob(pattern)
                expanded_tokens.extend(sorted(matches) if matches else [pattern])
            else:
                expanded_tokens.append(self._remove_quotes(token) if remove else token)

        return expanded_tokens

    # -- units ---------------------------------------------------------------

    def parse(self) -> list[dict]:
        """
        Returns a list of logical units.
        Each unit is a dictionary:
        {
            "pipeline": list of commands,
            "logic": "&&" | "||" | ";" | None (operator to evaluate AFTER this pipeline)
        }
        """
        units = list(self.iter_units())
        if not units:
            raise ParseError("Empty command")
        return units

    def iter_units(self) -> Iterator[dict]:
        """Yield logical units one at a time, tokenizing lazily.

        Expansion of a unit (`$?`, `$(...)`, globs) happens only when the
        previous unit has been consumed, so `false; echo $?` sees the
        status of `false` — the shell executes each unit before pulling
        the next one. Syntax errors in later units surface only when
        reached, like in an interactive bash.
        """
        produced = yield from self._units(self.text, frozenset())
        if not produced:
            raise ParseError("Empty command")

    def _units(self, text: str, chain: frozenset, tail_logic: Optional[str] = None,
               tail_background: bool = False):
        """Units of ``text``; returns how many were produced.

        ``tail_logic``/``tail_background`` belong to the unit this text
        replaced (an alias body): they attach to its last command, so
        ``x && y`` with ``alias x='a; b'`` runs ``a; b && y``.
        """
        segments = self._split_logic(text)
        if tail_logic is not None or tail_background:
            for idx in range(len(segments) - 1, -1, -1):
                seg_text, logic_op, background = segments[idx]
                if seg_text.strip():
                    segments[idx] = (seg_text, tail_logic, background or tail_background)
                    break

        produced = 0
        for segment_text, logic_op, background in segments:
            if not segment_text.strip():
                if logic_op and produced:
                    raise ParseError(f"Empty command near {logic_op}")
                continue  # a leading `;` or trailing operator: nothing to run

            expansion = self._expand_alias_text(segment_text, chain)
            if expansion is not None:
                new_text, names = expansion
                if not new_text.strip():
                    continue  # an empty alias expands to nothing
                produced += yield from self._units(
                    new_text, chain | names, logic_op, background
                )
                continue

            commands = self._build_pipeline(segment_text, background)
            if commands:
                produced += 1
                yield {"pipeline": commands, "logic": logic_op}
        return produced

    def _build_pipeline(self, segment_text: str, background: bool) -> list[dict]:
        pipeline_segments = self._split_by_pipe(segment_text)
        commands: list[dict] = []
        for pipe_seg in pipeline_segments:
            toks = self._tokenize(pipe_seg)
            if not toks:
                continue
            args_raw, spec = self._extract_redirections(toks)

            if not args_raw:
                raise ParseError("Missing command name")

            final_args = self._expand_words(args_raw)
            for key in ("stdin_file", "stdout_file", "stderr_file"):
                if spec[key]:
                    spec[key] = self._expand_word(spec[key])

            is_last = len(commands) == len(pipeline_segments) - 1
            spec["background"] = background and is_last

            # `command CMD ARGS` bypasses builtins (aliases were already
            # not expanded past the first word). `-v`/`-V` are handled by
            # the `command` builtin itself.
            spec["force_external"] = False
            if (
                final_args[0] == "command"
                and len(final_args) > 1
                and not final_args[1].startswith("-")
            ):
                final_args = final_args[1:]
                spec["force_external"] = True

            commands.append({"name": final_args[0], "args": final_args[1:], **spec})
        return commands
