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

from pydantic import BaseModel


OPENAPI_CACHE = {}


def with_cache_openapi_schema(schema: type[BaseModel], lang: str = None) -> dict:
    """
    Caching OpenAPI schemas of Pydantic models
    :param schema:
    :param lang:
    :return:

    Tags: RAG
    """
    schema_name = schema.schema_name
    if lang:
        schema_name = f'{schema_name}__{lang}'

    # if schema_name in OPENAPI_CACHE:
    #     return OPENAPI_CACHE[schema_name]

    # openapi = schema.schema()
    openapi = schema.model_json_schema()
    # if settings.BAZIS_SCHEMA_WITHOUT_REF:
    #     openapi = jsonref.replace_refs(openapi, lazy_load=False, proxies=False)
    OPENAPI_CACHE[schema_name] = openapi
    return openapi
