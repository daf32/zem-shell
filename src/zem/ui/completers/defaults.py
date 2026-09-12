import os
import stat
from typing import Iterable, List

from prompt_toolkit.completion import CompleteEvent, Completion, PathCompleter
from prompt_toolkit.document import Document

from zem.ui.completers.base import BaseArgCompleter


def _text_ends_with_space(document: Document) -> bool:
    """Check if the text before cursor ends with a space."""
    return document.text_before_cursor.endswith(" ")


def _get_file_type_info(path: str) -> str:
    """Get file type information for display in completion."""
    try:
        expanded = os.path.expanduser(path)
        st = os.lstat(expanded)
        mode = st.st_mode
        
        if stat.S_ISDIR(mode):
            return "📁 dir"
        elif stat.S_ISLNK(mode):
            # Check if symlink target exists
            if os.path.exists(expanded):
                if os.path.isdir(expanded):
                    return "🔗 → dir"
                return "🔗 → file"
            return "🔗 broken"
        elif stat.S_ISREG(mode):
            # Show file size for regular files
            size = st.st_size
            if size < 1024:
                return f"📄 {size}B"
            elif size < 1024 * 1024:
                return f"📄 {size // 1024}K"
            else:
                return f"📄 {size // (1024 * 1024)}M"
        elif stat.S_ISCHR(mode):
            return "⚡ char"
        elif stat.S_ISBLK(mode):
            return "💾 block"
        elif stat.S_ISFIFO(mode):
            return "📨 pipe"
        elif stat.S_ISSOCK(mode):
            return "🔌 socket"
        return "❓"
    except (OSError, IOError):
        return ""


def _current_word(text: str) -> str:
    """The word under the cursor: text after the last unescaped blank."""
    i = len(text)
    while i > 0:
        if text[i - 1].isspace() and not (i >= 2 and text[i - 2] == "\\"):
            break
        i -= 1
    return text[i:]


class EnhancedPathCompleter(PathCompleter):
    """PathCompleter with file type metadata in completion display.

    prompt_toolkit's PathCompleter treats the *entire* text before the
    cursor as the path, so it only ever worked when the path was the
    whole line. This wrapper completes the current word instead, which
    is what an argument position needs.
    """

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Get path completions (for the current word) with file type info."""
        word = _current_word(document.text_before_cursor)
        sub_document = Document(word, len(word))
        for completion in super().get_completions(sub_document, complete_event):
            # start_position is relative to the cursor, so it stays valid
            # for the full document.
            path_start = len(word) + completion.start_position
            prefix = word[:path_start] if path_start >= 0 else ""
            full_path = prefix + completion.text
            
            # If it's a relative path, make it relative to cwd
            if not full_path.startswith('/') and not full_path.startswith('~'):
                full_path = os.path.join(os.getcwd(), full_path)
            
            # Get file type info
            file_info = _get_file_type_info(full_path)
            
            yield Completion(
                text=completion.text,
                start_position=completion.start_position,
                display=completion.display,
                display_meta=file_info if file_info else completion.display_meta,
                style=completion.style,
                selected_style=completion.selected_style,
            )


class DirectoryCompleter(BaseArgCompleter):
    """Completes only directory paths with metadata."""

    fallback_to_paths = False  # "no matching directory" must not offer files
    
    def __init__(self):
        self._completer = EnhancedPathCompleter(expanduser=True, only_directories=True)
    
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        """Complete directory paths."""
        complete_event = CompleteEvent(text_inserted=False, completion_requested=True)
        return self._completer.get_completions(document, complete_event)


#: The four tool completers that used to live here are now JSON specs in
#: `zem/hints/data/`. Importing them by name should say so rather than
#: raising a bare AttributeError.
_MOVED = {
    "GitCompleter": "git",
    "PipCompleter": "pip",
    "DockerCompleter": "docker",
    "NpmCompleter": "npm",
}


def __getattr__(name: str):
    if name in _MOVED:
        raise AttributeError(
            f"{name} was replaced by the hint-spec engine; the data now lives "
            f"in zem/hints/data/{_MOVED[name]}.json — see docs/HINT_SPECS.md"
        )
    raise AttributeError(name)
