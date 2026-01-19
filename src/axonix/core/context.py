import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from axonix.builtins.base import BaseCommand


class ExecutionContext(BaseModel):
    """Shell execution context with proper typing."""
    history: List[str] = Field(default_factory=list)
    variables: Dict[str, str] = Field(default_factory=lambda: dict(os.environ))
    running: bool = True
    commands: Dict[str, BaseCommand] = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)
    last_exit_code: int = 0
    
    @field_validator('variables', mode='before')
    @classmethod
    def sync_environment_variables(cls, v):
        """Sync with os.environ on initialization."""
        if isinstance(v, dict):
            # Merge with current environment
            env = dict(os.environ)
            env.update(v)
            return env
        return v
    
    def sync_to_environment(self):
        """Sync variables to os.environ."""
        for key, value in self.variables.items():
            os.environ[key] = value
    
    def sync_from_environment(self):
        """Sync os.environ to variables."""
        self.variables.update(os.environ)
    
    class Config:
        arbitrary_types_allowed = True  # Allow BaseCommand instances