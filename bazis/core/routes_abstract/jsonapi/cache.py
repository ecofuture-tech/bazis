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
