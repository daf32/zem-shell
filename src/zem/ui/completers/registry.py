from typing import Dict

from zem.ui.completers.base import BaseArgCompleter


class CompleterRegistry:
    """Maps command names to argument completers.

    One instance per `ZemCompleter` (i.e. per shell). It used to be a
    class-level dict shared by every shell in the process, which made
    tests and multiple shell instances clobber each other.
    """

    def __init__(self) -> None:
        self._completers: Dict[str, BaseArgCompleter] = {}

    def register(self, command_name: str, completer: BaseArgCompleter) -> None:
        self._completers[command_name] = completer

    def unregister(self, command_name: str) -> None:
        self._completers.pop(command_name, None)

    def get(self, command_name: str) -> BaseArgCompleter | None:
        return self._completers.get(command_name)

    def get_all(self) -> Dict[str, BaseArgCompleter]:
        return dict(self._completers)
