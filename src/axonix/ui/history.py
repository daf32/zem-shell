"""prompt_toolkit history backend with a `clear()` that also empties the file."""

from prompt_toolkit.history import FileHistory


class AxonixFileHistory(FileHistory):
    def clear(self) -> None:
        """Forget every stored entry, in memory and on disk."""
        with open(self.filename, "wb"):
            pass  # truncate
        # Reset the base class's lazy-load cache so the arrow keys don't
        # keep serving the old entries.
        self._loaded_strings = []
        self._loaded = True
