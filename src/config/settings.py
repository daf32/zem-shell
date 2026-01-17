import os
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class OperatorsConfig(BaseModel):
    variable: str = "$"
    pipe: str = "|"
    quote: str = "'"
    double_quote: str = "\""
    space: str = " "
    semicolon: str = ";"
    comment: str = "#"
    redirect_output: str = ">"
    redirect_input: str = "<"
    background: str = "&"
    variable_start: str = "{"
    variable_end: str = "}"
    escape: str = "\\"

class InputSettings(BaseModel):
    prompt: str = ">>>"
    show_full_path: bool = False
    path_depth: int = Field(default=2, ge=0)

class ShellSettings(BaseModel):
    input: InputSettings = Field(default_factory=InputSettings)

class AppConfig(BaseSettings):
    operators: OperatorsConfig = Field(default_factory=OperatorsConfig)
    settings: ShellSettings = Field(default_factory=ShellSettings)

    model_config = SettingsConfigDict(
        json_file=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.json")),
        json_file_encoding='utf-8',
        extra='ignore'
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings
    ):
        from pydantic_settings import JsonConfigSettingsSource
        return (
            init_settings,
            JsonConfigSettingsSource(settings_cls),
            env_settings,
        )

config = AppConfig()
