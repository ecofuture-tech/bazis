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


def test_own_required_keeps_the_disabled_field(factories):
    """
    A field whose own restrictions say `required` stays in the schema although `__all__`
    (or the field itself) disables it, as before bazis 2.16: the permission names the field.
    """
    from bazis.core.schemas.enums import CrudApiAction

    for action in (CrudApiAction.UPDATE, CrudApiAction.CREATE):
        factory = factories[action]
        fields = {
            f.name: f
            for f in factory.fields_patch(
                {'__all__': {'disable'}, OPTIONAL: {'required', 'notnull'}}
            )
        }
        assert set(fields) == {OPTIONAL} | ({REQUIRED} if action == CrudApiAction.CREATE else set())
        assert fields[OPTIONAL].required
        assert fields[OPTIONAL].nullable is False
        assert OPTIONAL in names(factory, {OPTIONAL: {'required', 'disable'}})

    # in a view the restrictions of requiredness do not apply: the field is hidden
    assert names(factories[CrudApiAction.RETRIEVE], {'__all__': {'disable'}, OPTIONAL: {'required'}}) == set()


def test_required_of_all_does_not_keep_a_disabled_field(factories):
    """`__all__.required` with `<field>.disable`: the field is hidden from an update."""
    from bazis.core.schemas.enums import CrudApiAction

    restricts = {'__all__': {'required'}, REQUIRED: {'disable'}, OPTIONAL: {'disable'}}
    shown = names(factories[CrudApiAction.UPDATE], restricts)
    assert REQUIRED not in shown
    assert OPTIONAL not in shown
    assert 'child_is_active' in shown
    # the create keeps the fields required there, by the model or by `__all__` (as before)
    shown = names(factories[CrudApiAction.CREATE], restricts)
    assert {REQUIRED, OPTIONAL} <= shown


def test_own_required_keeps_the_disabled_field_in_another_action(sample_app):
    """
    An operation of a package (the transit of bazis-statusy, which validates the stored
    item): its own `required` keeps a field `__all__` disables, the requiredness of the
    model alone does not.
    """
    from functools import cached_property

    from entity.routes import ChildEntityRouteSet

    from bazis.core.schemas.enums import AccessAction, ApiAction
    from bazis.core.schemas.factory import SchemaFactory

    class Access(AccessAction):
        CHECKUP = 'checkup'

    class Action(ApiAction):
        CHECKUP = 'checkup'

        @cached_property
        def access_action(self):
            return Access.CHECKUP

    factory = SchemaFactory(
        route_cls=ChildEntityRouteSet, model=ChildEntityRouteSet.model, api_action=Action.CHECKUP
    )
    assert names(factory, {'__all__': {'disable'}, OPTIONAL: {'required', 'notnull'}}) == {OPTIONAL}
    assert names(factory, {'__all__': {'disable'}}) == set()
    assert names(factory, {'__all__': {'required'}, OPTIONAL: {'disable'}}) >= {REQUIRED}
    assert OPTIONAL not in names(factory, {'__all__': {'required'}, OPTIONAL: {'disable'}})
