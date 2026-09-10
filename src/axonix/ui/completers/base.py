from abc import ABC, abstractmethod
from typing import Iterable, List

from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document


class BaseArgCompleter(ABC):
    """Base class for argument completers."""
    
    @abstractmethod
    def get_completions(
        self, document: Document, parts: List[str], word_before: str
    ) -> Iterable[Completion]:
        """Get completions for the current argument.
        
        Args:
            document: The full document being edited.
            parts: The command line split into parts (including the command itself).
            word_before: The word currently being typed (under cursor).
            
        Returns:
            Iterable of Completion objects.
        """
        pass
