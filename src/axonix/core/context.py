import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from axonix.builtins.base import BaseCommand


class ExecutionContext(BaseModel):
    """Shell execution context.

    Variable model
    --------------
    ``variables`` holds *every* shell variable. ``exported`` is the subset of
    names that children inherit. ``os.environ`` is kept as an eager mirror of
    the exported subset (many stdlib/prompt_toolkit paths read it directly:
    ``shutil.which``, ``os.path.expanduser``, ...). Nothing outside this
    class should write ``os.environ``; use :meth:`set_var` and friends.

    At construction ``variables`` and ``exported`` are both seeded from the
    process environment, so inherited names such as ``PATH`` stay exported
    when reassigned. New names created via :meth:`set_var` are shell-local
    until :meth:`export_var` promotes them. The ``?`` pseudo-variable is
    never exported.
    """

    history: List[str] = Field(default_factory=list)
    variables: Dict[str, str] = Field(default_factory=lambda: dict(os.environ))
    exported: Optional[set[str]] = None
    running: bool = True
    exit_status: int = 0
    commands: Dict[str, BaseCommand] = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)
    active_venv: str | None = Field(default_factory=lambda: os.environ.get("VIRTUAL_ENV"))
    original_path: str = Field(default_factory=lambda: os.environ.get("PATH", ""))

    # Use PrivateAttr for internal state that shouldn't be in model
    _last_exit_code: int = PrivateAttr(default=0)
    _background_processes: List = PrivateAttr(default_factory=list)
    _dir_stack: List[str] = PrivateAttr(default_factory=list)  # pushd/popd
    _shell: Any = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def _default_exported(self):
        """When ``exported`` isn't given, every initial variable is exported.

        This keeps the default (``variables`` seeded from ``os.environ``)
        consistent, and makes an explicitly passed ``variables`` dict
        hermetic: nothing from the real environment leaks in.
        """
        if self.exported is None:
            self.exported = set(self.variables)
        return self

    # -- variable API -------------------------------------------------------

    def set_var(self, name: str, value: str, *, export: bool | None = None) -> None:
        """Assign ``name``.

        ``export=None`` keeps the current export status (an already exported
        name stays exported, a new name is shell-local). ``True``/``False``
        force it.
        """
        self.variables[name] = value
        if export is True:
            self.exported.add(name)
        elif export is False:
            self.exported.discard(name)

        if name in self.exported:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)

    def unset_var(self, name: str) -> None:
        self.variables.pop(name, None)
        self.exported.discard(name)
        os.environ.pop(name, None)

    def export_var(self, name: str) -> None:
        """Promote ``name`` to the environment, creating it empty if needed."""
        value = self.variables.setdefault(name, "")
        self.exported.add(name)
        os.environ[name] = value

    def unexport_var(self, name: str) -> None:
        self.exported.discard(name)
        os.environ.pop(name, None)

    def is_exported(self, name: str) -> bool:
        return name in self.exported

    def child_env(self) -> Dict[str, str]:
        """Environment for child processes: exported variables only."""
        return {k: self.variables[k] for k in self.exported if k in self.variables}

    # -- exit code ----------------------------------------------------------

    @property
    def last_exit_code(self) -> int:
        """Get last exit code."""
        return self._last_exit_code

    @last_exit_code.setter
    def last_exit_code(self, value: int):
        """Set last exit code and update the shell-local ``?`` variable."""
        self._last_exit_code = value
        self.variables["?"] = str(value)
