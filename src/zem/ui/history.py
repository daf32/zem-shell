"""The history file, shared by the prompt (arrows, Ctrl-R) and the shell.

prompt_toolkit's `FileHistory` appends every accepted line as it is
entered; this subclass adds what the shell needs on top: creating the
file private to the user, honouring the config switches, and trimming
the file to a size.
"""

import os
import time

from prompt_toolkit.history import FileHistory


class ZemFileHistory(FileHistory):
    def __init__(self, filename: str, *, load: bool = True, persist: bool = True) -> None:
        """
        ``load=False`` starts the session with an empty history (the file
        is left alone); ``persist=False`` keeps new entries in memory only.
        """
        super().__init__(filename)
        self._load_file = load
        self._persist = persist
        if persist:
            self._create_private()

    def _create_private(self) -> None:
        """Create the file readable by the owner only (like bash's).

        Command lines carry tokens and passwords; an existing file keeps
        whatever permissions the user gave it.
        """
        try:
            fd = os.open(self.filename, os.O_WRONLY | os.O_CREAT, 0o600)
        except OSError:
            return
        os.close(fd)

    # -- prompt_toolkit hooks -------------------------------------------------

    def load_history_strings(self):
        if not self._load_file:
            return iter(())
        return super().load_history_strings()

    def store_string(self, string: str) -> None:
        if self._persist:
            super().store_string(string)

    # -- the shell's own operations -------------------------------------------

    def entries(self) -> list[str]:
        """Every line in the file, oldest first, regardless of ``load``."""
        return list(reversed(list(super().load_history_strings())))

    def clear(self) -> None:
        """Forget every stored entry, in memory and on disk."""
        with open(self.filename, "wb"):
            pass  # truncate
        # Reset the base class's lazy-load cache so the arrow keys don't
        # keep serving the old entries.
        self._loaded_strings = []
        self._loaded = True

    def rotate(self, max_entries: int) -> None:
        """Rewrite the file with its last ``max_entries`` lines."""
        if not self._persist:
            return
        try:
            entries = self.entries()
        except OSError:
            return
        if len(entries) <= max_entries:
            return
        self.rewrite(entries[-max_entries:])

    def rewrite(self, entries: list[str]) -> None:
        """Replace the file's content with ``entries`` (oldest first)."""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, "wb") as handle:
            for entry in entries:
                body = "".join(f"+{line}\n" for line in entry.split("\n"))
                handle.write(f"\n# {stamp}\n{body}".encode("utf-8"))
