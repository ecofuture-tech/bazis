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

"""
`SchemaFactory.fields_patch`: `disable` hides a field from every schema whatever its
requiredness in the model, except a required field in the schema of a create (an item
cannot be created without it). `readonly`, `writeonly` and `enable` replace `disable`.
"""

import pytest


REQUIRED = 'child_name'
OPTIONAL = 'child_description'


def names(factory, restricts: dict[str, set[str]]) -> set[str]:
    return {f.name for f in factory.fields_patch({k: set(v) for k, v in restricts.items()})}


@pytest.fixture
def factories(sample_app):
    from entity.routes import ChildEntityRouteSet

    from bazis.core.schemas.enums import CrudApiAction

    return {
        action: ChildEntityRouteSet.schema_factories[action]
        for action in CrudApiAction
        if action in ChildEntityRouteSet.schema_factories
    }


def test_required_field_is_required(factories):
    from bazis.core.schemas.enums import CrudApiAction

    fields = factories[CrudApiAction.CREATE].fields
    assert fields[REQUIRED].required
    assert not fields[OPTIONAL].required


@pytest.mark.parametrize('field', [REQUIRED, OPTIONAL])
def test_disable_hides_from_update_and_view(factories, field):
    from bazis.core.schemas.enums import CrudApiAction

    for action in (CrudApiAction.UPDATE, CrudApiAction.RETRIEVE, CrudApiAction.LIST):
        shown = names(factories[action], {field: {'disable'}})
        assert field not in shown, action
        assert {REQUIRED, OPTIONAL} - {field} <= shown, action


def test_disable_on_create_keeps_only_the_required_field(factories):
    from bazis.core.schemas.enums import CrudApiAction

    factory = factories[CrudApiAction.CREATE]
    assert REQUIRED in names(factory, {REQUIRED: {'disable'}})
    assert OPTIONAL not in names(factory, {OPTIONAL: {'disable'}})
    shown = names(factory, {'__all__': {'disable'}})
    assert REQUIRED in shown
    assert OPTIONAL not in shown


def test_disable_of_all_fields_on_update(factories):
    """`__all__.disable` hides the required fields too; a field's own `enable` shows it."""
    from bazis.core.schemas.enums import CrudApiAction

    factory = factories[CrudApiAction.UPDATE]
    assert names(factory, {'__all__': {'disable'}}) == set()
    assert names(factory, {'__all__': {'disable'}, REQUIRED: {'enable'}}) == {REQUIRED}


@pytest.mark.parametrize('restrict', ['enable', 'readonly', 'writeonly'])
def test_shown_restriction_replaces_disable_on_update(factories, restrict):
    from bazis.core.schemas.enums import CrudApiAction

    factory = factories[CrudApiAction.UPDATE]
    fields = {f.name: f for f in factory.fields_patch({REQUIRED: {'disable', restrict}})}
    assert REQUIRED in fields
    assert bool(fields[REQUIRED].read_only) is (restrict == 'readonly')


def test_inclusion_of_the_update_hides_the_disabled_required_field(sample_app):
    """The schemas of the objects `included` in an update (their factories) hide it too."""
    from entity.routes import ParentEntityRouteSet

    from bazis.core.schemas.enums import CrudApiAction

    factory = ParentEntityRouteSet.schema_factories[CrudApiAction.UPDATE]
    inclusion = factory.inclusions_factory_with_default['dependent_entities']
    assert inclusion.fields['dependent_name'].required
    assert 'dependent_name' not in names(inclusion, {'dependent_name': {'disable'}})

    create = ParentEntityRouteSet.schema_factories[CrudApiAction.CREATE]
    inclusion = create.inclusions_factory_with_default['dependent_entities']
    assert 'dependent_name' in names(inclusion, {'dependent_name': {'disable'}})
