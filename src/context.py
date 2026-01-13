from dataclasses import dataclass, field
from typing import Dict
from src.commands.base import BaseCommand

@dataclass
class ExecutionContext:
    history: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    running: bool = True
    commands: Dict[str, BaseCommand] = field(default_factory=dict)