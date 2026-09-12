"""The HintSpec schema: pydantic models for a completion spec."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

#: Bumped whenever the schema changes in a way older Zem cannot read. A spec
#: declaring a higher version is refused with a clear message instead of
#: being half-understood.
CURRENT_SCHEMA_VERSION = 1


class SpecError(ValueError):
    """A spec document could not be turned into a `HintSpec`."""


class _Model(BaseModel):
    # Specs are written by hand, by people who are not us. A typo like
    # "subcommand" must fail loudly rather than be silently ignored;
    # forward compatibility is what `schema_version` is for.
    model_config = ConfigDict(extra="forbid")


class Choice(_Model):
    """One static value, with the text shown next to it in the menu."""

    value: str
    description: str = ""


class ValuesSource(_Model):
    """A fixed list of values written into the spec."""

    type: Literal["values"]
    items: list[Union[Choice, str]] = Field(min_length=1)

    def choices(self) -> list[Choice]:
        return [i if isinstance(i, Choice) else Choice(value=i) for i in self.items]


class FilesSource(_Model):
    type: Literal["files"]
    extensions: list[str] = []


class DirsSource(_Model):
    type: Literal["dirs"]


class CommandsSource(_Model):
    """Executables on PATH — for `docker exec <container> <TAB>`."""

    type: Literal["commands"]


class NoneSource(_Model):
    """Nothing to suggest here, and do not fall back to paths either."""

    type: Literal["none"]


class ParseSpec(_Model):
    """How to turn a command's stdout into values."""

    separator: Optional[str] = None
    value_column: int = Field(default=0, ge=0)
    description_column: Optional[int] = Field(default=1, ge=0)
    skip_lines: int = Field(default=0, ge=0)
    max_items: int = Field(default=200, ge=1, le=5000)


class Guard(_Model):
    """A cheap precondition checked before an expensive source runs.

    `git for-each-ref` outside a repository is pure waste; a guard of
    `git rev-parse --is-inside-work-tree` skips it.
    """

    run: list[str] = Field(min_length=1)
    timeout_ms: int = Field(default=200, ge=1, le=2000)
    cache_ttl_ms: int = Field(default=5000, ge=0, le=600_000)


class CommandSource(_Model):
    """Values from the stdout of an external command."""

    type: Literal["command"]
    run: list[str] = Field(min_length=1)
    timeout_ms: int = Field(default=300, ge=1, le=2000)
    cache_ttl_ms: int = Field(default=2000, ge=0, le=600_000)
    cache_scope: Literal["cwd", "global"] = "cwd"
    accept_nonzero: bool = False
    min_prefix: int = Field(default=0, ge=0, le=8)
    parse: ParseSpec = Field(default_factory=lambda: ParseSpec())
    guard: Optional[Guard] = None

    @field_validator("run")
    @classmethod
    def _no_interpolation(cls, value: list[str]) -> list[str]:
        # Splicing what the user is typing into an argv would make a spec an
        # injection vector. Anything that needs the current input writes a
        # provider instead, where the code is reviewable.
        for arg in value:
            if "{" in arg and "}" in arg:
                raise ValueError(
                    f"placeholders are not supported in `run` ({arg!r}); "
                    "use a named provider for input-dependent values"
                )
        return value


class ProviderSource(_Model):
    """Values from a named Python provider registered by Zem or a plugin."""

    type: Literal["provider"]
    name: str = Field(pattern=r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
    args: dict[str, Any] = {}
    min_prefix: int = Field(default=0, ge=0, le=8)


class AnyOfSource(_Model):
    """Several sources at once — git branches *and* files, say."""

    type: Literal["any_of"]
    sources: list["ValueSource"] = Field(min_length=2)


ValueSource = Annotated[
    Union[
        ValuesSource,
        FilesSource,
        DirsSource,
        CommandsSource,
        NoneSource,
        CommandSource,
        ProviderSource,
        AnyOfSource,
    ],
    Field(discriminator="type"),
]


def _default_files() -> FilesSource:
    return FilesSource(type="files")


class Option(_Model):
    """A flag. All spellings of one flag live in a single entry."""

    names: list[str] = Field(min_length=1)
    description: str = ""
    #: None -> the flag takes no value. `{"type": "none"}` -> it takes one,
    #: but we have nothing to suggest for it.
    value: Optional[ValueSource] = None
    repeatable: bool = False
    #: Visible in every nested subcommand (`git -C`, `docker --context`).
    inherited: bool = False
    hidden: bool = False

    @field_validator("names")
    @classmethod
    def _dash_prefixed(cls, value: list[str]) -> list[str]:
        for name in value:
            if not name.startswith("-") or name in ("-", "--"):
                raise ValueError(f"option name must start with a dash: {name!r}")
        return value


class Positional(_Model):
    """A positional argument."""

    name: str = "arg"
    description: str = ""
    source: ValueSource = Field(default_factory=_default_files)
    #: Repeats until the end of the command (`git add a b c`).
    variadic: bool = False


class _NodeBase(_Model):
    description: str = ""
    options: list[Option] = []
    args: list[Positional] = []

    @model_validator(mode="after")
    def _variadic_comes_last(self):
        for arg in self.args[:-1]:
            if arg.variadic:
                raise ValueError(
                    f"only the last positional may be variadic, {arg.name!r} is not last"
                )
        return self


class Node(_NodeBase):
    """A subcommand. Nests to any depth, so `docker container ls` works."""

    name: str
    aliases: list[str] = []
    hidden: bool = False
    subcommands: list["Node"] = []


class HintSpec(_NodeBase):
    """A whole spec document: one command and everything under it."""

    schema_version: int = Field(ge=1)
    command: str = Field(min_length=1)
    #: Other names this spec answers to (`pip3`, `podman`).
    aliases: list[str] = []
    #: What to offer in a position the spec does not describe.
    fallback: Literal["files", "dirs", "none"] = "files"
    subcommands: list[Node] = []

    #: Filled in by the loader, never read from JSON.
    origin: Literal["bundled", "user", "plugin"] = Field(default="bundled", exclude=True)
    source_path: str = Field(default="", exclude=True)

    @field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: int) -> int:
        if value > CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"spec needs schema_version {value}, this zem understands "
                f"{CURRENT_SCHEMA_VERSION} — upgrade zem to use it"
            )
        return value

    def names(self) -> list[str]:
        """Every command name this spec should be registered under."""
        return [self.command, *self.aliases]


AnyOfSource.model_rebuild()
Node.model_rebuild()


def parse_spec(data: Any) -> HintSpec:
    """Validate a decoded JSON document into a `HintSpec`.

    Raises `SpecError` with one `loc: msg` line per problem, which is what
    the loader shows and what `zem` prints for a broken user spec.
    """
    if not isinstance(data, dict):
        raise SpecError("spec must be a JSON object")
    try:
        return HintSpec.model_validate(data)
    except ValidationError as exc:
        from zem.config.settings import format_validation_error

        raise SpecError(format_validation_error(exc)) from exc
