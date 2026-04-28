import os
from typing import Dict, List, Any
from pydantic import BaseModel, Field, field_validator, PrivateAttr, ConfigDict
from axonix.builtins.base import BaseCommand


class ExecutionContext(BaseModel):
    """Shell execution context with proper typing."""
    history: List[str] = Field(default_factory=list)
    variables: Dict[str, str] = Field(default_factory=lambda: dict(os.environ))
    running: bool = True
    commands: Dict[str, BaseCommand] = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)
    active_venv: str | None = Field(default=os.environ.get("VIRTUAL_ENV"))
    original_path: str = os.environ["PATH"]
    
    # Use PrivateAttr for internal state that shouldn't be in model
    _last_exit_code: int = PrivateAttr(default=0)
    _background_processes: List = PrivateAttr(default_factory=list)
    _shell: Any = PrivateAttr(default=None)
    
    @field_validator('variables', mode='before')
    @classmethod
    def sync_environment_variables(cls, v):
        """Sync with os.environ on initialization."""
        if isinstance(v, dict):
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
        # Also update PATH with fresh value if available
        try:
            import subprocess
            shell = self.variables.get('SHELL', '/bin/bash')
            result = subprocess.run(
                [shell, '-c', 'echo $PATH'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                fresh_path = result.stdout.strip()
                if fresh_path:
                    self.variables['PATH'] = fresh_path
                    os.environ['PATH'] = fresh_path
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            pass
    
    @property
    def last_exit_code(self) -> int:
        """Get last exit code."""
        return self._last_exit_code
    
    @last_exit_code.setter
    def last_exit_code(self, value: int):
        """Set last exit code and update ? variable."""
        self._last_exit_code = value
        self.variables["?"] = str(value)

    model_config = ConfigDict(arbitrary_types_allowed=True)
