import os
from dataclasses import dataclass, field
from typing import Dict
from axonix.builtins.base import BaseCommand

@dataclass
class ExecutionContext: 
    history: list = field(default_factory=list)
    variables: dict = field(default_factory=lambda: os.environ.copy())
    running: bool = True
    commands: Dict[str, BaseCommand] = field(default_factory=dict)