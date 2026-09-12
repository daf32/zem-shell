"""`SpecCompleter`: the one completer that runs every hint spec."""

from __future__ import annotations

import os
import time
from typing import Iterable, List

from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document

from zem.core.scan import split_words
from zem.hints.resolver import Resolution, resolve
from zem.hints.sources import SourceContext, Suggestion
from zem.hints.sources import resolve as resolve_source
from zem.hints.spec import AnyOfSource, DirsSource, FilesSource, HintSpec, NoneSource
from zem.ui.completers.base import BaseArgCompleter
from zem.ui.completers.defaults import EnhancedPathCompleter

#: Ceiling for one completion round. Past it we stop starting new dynamic
#: sources; the static ones have already been yielded.
BUDGET_SECONDS = 0.5


class SpecCompleter(BaseArgCompleter):
    """Completes a command from its `HintSpec`.

    Where the four hand-written completers each re-derived the cursor
    position from `len(parts)` and a trailing-space check — and disagreed
    with each other about it — this walks the spec once and asks the
    resolver.
    """

    #: The spec says what happens in a position it does not describe, so
    #: the shell's "produced nothing, try paths" heuristic must stay out.
    fallback_to_paths = False

    def __init__(self, spec: HintSpec, shell=None):
        self.spec = spec
        self.shell = shell
        self._paths = EnhancedPathCompleter(expanduser=True)
        self._dirs = EnhancedPathCompleter(expanduser=True, only_directories=True)

    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        prefix = self._value_of(word_before)
        cursor_index = len(parts) - 1 if word_before else len(parts)
        res = resolve(self.spec, parts, cursor_index, prefix)

        if res.redirect_target:
            yield from self._paths_for(document, self._paths)
            return

        started = time.monotonic()
        replace = -(len(word_before) - res.value_offset)
        # For `--mode=de` only `de` is the value being completed.
        prefix = prefix[res.value_offset:]

        # Static first: prompt_toolkit stops pulling this generator as soon
        # as the next keystroke arrives, so a cancelled round should lose
        # the expensive part, not the cheap one.
        if res.offer_flags:
            yield from self._emit(_flag_choices(res), prefix, replace)
            return

        emitted = False
        if res.offer_subcommands:
            for completion in self._emit(_subcommand_choices(res), prefix, replace):
                emitted = True
                yield completion

        for source in res.sources:
            for completion in self._from_source(source, document, res, prefix, replace, started):
                emitted = True
                yield completion

        if not emitted and not res.sources:
            yield from self._fallback(document)

    # -- sources -----------------------------------------------------------

    def _from_source(self, source, document, res, prefix, replace, started):
        if isinstance(source, AnyOfSource):
            for nested in source.sources:
                yield from self._from_source(nested, document, res, prefix, replace, started)
            return
        if isinstance(source, FilesSource):
            yield from self._paths_for(document, self._paths, source.extensions)
            return
        if isinstance(source, DirsSource):
            yield from self._paths_for(document, self._dirs)
            return
        if isinstance(source, NoneSource):
            return
        if time.monotonic() - started > BUDGET_SECONDS:
            return
        yield from self._emit(resolve_source(source, self._context(res, prefix)), prefix, replace)

    def _context(self, res: Resolution, prefix: str) -> SourceContext:
        settings = getattr(getattr(self.shell, "config", None), "hints", None)
        return SourceContext(
            cwd=os.getcwd(),
            shell=self.shell,
            node_path=res.path,
            prefix=prefix,
            settings=settings,
        )

    def _fallback(self, document: Document) -> Iterable[Completion]:
        if self.spec.fallback == "files":
            return self._paths_for(document, self._paths)
        if self.spec.fallback == "dirs":
            return self._paths_for(document, self._dirs)
        return ()

    def _paths_for(self, document: Document, completer, extensions=()) -> Iterable[Completion]:
        event = CompleteEvent(text_inserted=False, completion_requested=True)
        for completion in completer.get_completions(document, event):
            if extensions and not completion.text.endswith(tuple(extensions)):
                # Directories still matter: they are how you reach the file.
                if not completion.display_meta_text.startswith("📁"):
                    continue
            yield completion

    # -- emitting ----------------------------------------------------------

    def _emit(self, suggestions: Iterable[Suggestion], prefix: str,
              replace: int) -> Iterable[Completion]:
        for suggestion in suggestions:
            if prefix and not suggestion.value.startswith(prefix):
                continue
            yield Completion(
                _quote_if_needed(suggestion.value),
                start_position=replace,
                display=suggestion.value,
                display_meta=suggestion.description,
            )

    def _value_of(self, word: str) -> str:
        """The word under the cursor with its quoting resolved."""
        if not word:
            return ""
        ops = getattr(getattr(self.shell, "config", None), "operators", None)
        if ops is None:
            return word
        words = split_words(word, ops)
        return words[0].value if words else ""


def _subcommand_choices(res: Resolution) -> list[Suggestion]:
    return [
        Suggestion(child.name, child.description)
        for child in getattr(res.node, "subcommands", ())
        if not child.hidden
    ]


def _flag_choices(res: Resolution) -> list[Suggestion]:
    seen: set[str] = set()
    out: list[Suggestion] = []
    for option in res.options:
        for name in option.names:
            if name not in seen:
                seen.add(name)
                out.append(Suggestion(name, option.description))
    return out


def _quote_if_needed(value: str) -> str:
    """Quote a value the shell would otherwise split or mangle."""
    if value and not any(ch in value for ch in ' \t"\'\\$`'):
        return value
    return "'" + value.replace("'", "'\\''") + "'"
