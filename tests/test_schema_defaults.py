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
import subprocess
import sys

from django.apps import apps

import pytest
from entity.routes import ExtendedEntityRouteSet, ParentEntityRouteSet

from bazis.core.schemas import cache as cache_module
from bazis.core.schemas.cache import TTLCache
from bazis.core.schemas.enums import CrudApiAction


DUMP_OPENAPI = (
    'import json, django; django.setup(); '
    'from bazis.core.app import app; '
    'print(json.dumps(app.openapi(), sort_keys=True))'
)


def test_openapi_is_identical_across_processes():
    """
    The generated OpenAPI is the contract frontend clients are generated from, so it must
    not depend on the time or the randomness of the process that built it (two different
    hash seeds: the order of the sets of strings differs between them).
    """
    env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'sample.settings'}
    processes = [
        subprocess.Popen(
            [sys.executable, '-c', DUMP_OPENAPI],
            env={**env, 'PYTHONHASHSEED': seed},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for seed in ('1', '2')
    ]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=300)
        assert process.returncode == 0, stderr
        outputs.append(stdout.splitlines()[-1])

    # the documents are megabytes long: do not let pytest diff them, show the first difference
    first, second = outputs
    same = first == second
    position = next((i for i, (a, b) in enumerate(zip(first, second, strict=False)) if a != b), 0)
    window = slice(max(position - 80, 0), position + 40)
    assert same, f'{first[window]!r} != {second[window]!r}'


def test_openapi_has_no_defaults_of_callable_model_defaults():
    from bazis.core.app import app

    schemas = app.openapi()['components']['schemas']
    created = [
        schema['properties']['dt_created']
        for name, schema in schemas.items()
        if name.endswith('__Attributes__Attributes') and 'dt_created' in schema['properties']
    ]
    assert created
    assert all('default' not in prop for prop in created)


@pytest.fixture
def fresh_schema_cache(monkeypatch):
    """
    Schemas are cached by name, so a schema of the changed model field must not be
    taken from or leaked to the cache of the other tests.
    """
    monkeypatch.setattr(cache_module, 'SCHEMAS_CACHE', TTLCache(0))


@pytest.fixture
def callable_default(monkeypatch, request, fresh_schema_cache):
    """
    Gives a model field a callable default (like the one of bazis-statusy that looks the
    initial status up in the database) and records its calls.
    """
    calls = []

    def patch(label, name):
        model_field = apps.get_model(label)._meta.get_field(name)
        monkeypatch.setattr(model_field, 'default', lambda: calls.append(name) or 'value')
        # Django caches the callable of the default in the field
        model_field.__dict__.pop('_get_default', None)
        request.addfinalizer(lambda: model_field.__dict__.pop('_get_default', None))

    return patch, calls


def build_resource_schemas(route_cls, api_action=CrudApiAction.CREATE):
    factory = route_cls.build_schema_factory(api_action)
    schema = factory.build_resource_schema()
    return (
        schema.model_fields['attributes'].annotation,
        schema.model_fields['relationships'].annotation,
    )


def test_callable_attribute_default_is_never_evaluated(callable_default):
    patch, calls = callable_default
    _, _ = build_resource_schemas(ParentEntityRouteSet)
    required = build_resource_schemas(ParentEntityRouteSet)[0].model_json_schema()['required']

    patch('entity.ParentEntity', 'description')
    attributes, _ = build_resource_schemas(ParentEntityRouteSet)

    # a callable default is optional, has no value in the schema and is not evaluated
    properties = attributes.model_json_schema()['properties']
    assert properties['description'].get('default') is None
    assert attributes.model_json_schema()['required'] == required
    value = attributes.model_validate({'name': 'one'})
    assert 'description' not in value.model_fields_set
    assert 'description' not in value.model_dump(exclude_unset=True)
    assert not calls


def test_callable_relation_default_is_never_evaluated(callable_default):
    patch, calls = callable_default

    patch('entity.ExtendedEntity', 'parent_entity')
    _, relationships = build_resource_schemas(ExtendedEntityRouteSet)

    # the relation and the id of its resource identifier stay optional, without a value
    schema = relationships.model_json_schema()
    assert 'parent_entity' not in schema.get('required', [])
    identifier = schema['$defs'][
        next(k for k in schema['$defs'] if k.endswith('ResourceIdentifierSchema__entity__parent_entity'))
    ]
    assert 'id' not in identifier.get('required', [])
    assert identifier['properties']['id'].get('default') is None
    relationships.model_validate({'parent_entity': {'data': {'type': 'entity.parent_entity'}}})
    relationships.model_validate({})
    assert not calls


def test_callable_default_is_not_evaluated_for_a_sparse_response(callable_default):
    patch, calls = callable_default

    patch('entity.ParentEntity', 'description')
    factory = ParentEntityRouteSet.build_schema_factory(CrudApiAction.LIST)
    attributes = factory.build_resource_schema_response().model_fields['attributes'].annotation

    value = attributes.model_validate({'name': 'one'})
    assert value.model_fields_set == {'name'}
    assert not calls


def test_static_model_default_stays_in_schema(fresh_schema_cache):
    attributes, _ = build_resource_schemas(ParentEntityRouteSet)

    assert attributes.model_json_schema()['properties']['state']['default'] == 'state_one'


def test_uuid_id_example_is_stable():
    model = apps.get_model('entity.ParentEntity')

    assert model.get_id_example() == model.get_id_example()
    assert model.get_id_example() != apps.get_model('entity.ChildEntity').get_id_example()
