from pydantic import BaseModel


SCHEMAS_CACHE: dict[str, type[BaseModel]] = {}


def get_schema_from_cache(key: str) -> type[BaseModel] | None:
    return SCHEMAS_CACHE.get(key)


def set_schema_to_cache(key: str, schema: type[BaseModel]) -> None:
    SCHEMAS_CACHE[key] = schema
