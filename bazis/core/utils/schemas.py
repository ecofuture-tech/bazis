import os
from typing import Any

from pydantic import BaseModel

from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonResourceSchema(BaseModel):
    """
    Base schema for resources with ID and type fields.
    Used for generic resource identification across the framework.
    Flexible ID type (Any) allows strings, integers, UUIDs, etc.
    """

    id: Any
    type: str


class BazisSettings(BaseSettings):
    """
    Core settings class for Bazis framework configuration.
    Loads from environment variables with 'BS_' prefix and .env files.

    Key features:
    - Prefix: BS_ for all env vars (e.g., BS_DEBUG)
    - Nested vars: Use __ delimiter (e.g., BS_DATABASE__HOST)
    - Files: Loads from project.env and custom file via BS_ENV_FILE
    - Case-sensitive variable names
    - Extra fields ignored

    Tags: RAG, EXPORT
    """

    model_config = SettingsConfigDict(
        extra='ignore',
        env_prefix='BS_',
        env_nested_delimiter='__',
        case_sensitive=True,
        env_file=('project.env', os.getenv('BS_ENV_FILE', '.env')),
    )
