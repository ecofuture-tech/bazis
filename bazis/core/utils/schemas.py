# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
