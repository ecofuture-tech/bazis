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

from urllib.parse import urlencode

import pytest
from bazis_test_utils.utils import get_api_client
from entity.models import (
    ChildEntity,
    DependentEntity,
    ExtendedEntity,
)

from bazis.core.models_abstract import InitialBase

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_routes_included(sample_app):
    parent_entity = factories.ParentEntityFactory.create(child_entities=True)

    query = urlencode(
        {
            'include': 'extended_entity,dependent_entities,child_entities',
        }
    )

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/parent_entity/{parent_entity.pk}/?{query}'
    )

    assert response.status_code == 200

    data = response.json()

    for include in data['included']:
        assert include['type'] in [
            'entity.extended_entity',
            'entity.dependent_entity',
            'entity.child_entity',
        ]
        assert include['id'] is not None
        assert 'attributes' in include
        assert 'relationships' in include

        obj = InitialBase.get_model_by_label(include['type']).objects.get(pk=include['id'])

        _attributes = include['attributes']
        _relationships = include['relationships']

        assert include['id'] == str(obj.id)
        assert _attributes['dt_created'] == obj.dt_created.isoformat().replace('+00:00', 'Z')
        assert _attributes['dt_updated'] == obj.dt_updated.isoformat().replace('+00:00', 'Z')

        if isinstance(obj, ExtendedEntity):
            assert _attributes['extended_name'] == obj.extended_name
            assert _attributes['extended_description'] == obj.extended_description
            assert _attributes['extended_is_active'] == obj.extended_is_active
            assert _attributes['extended_price'] == str(obj.extended_price)
            assert _attributes[
                'extended_dt_approved'
            ] == obj.extended_dt_approved.isoformat().replace('+00:00', 'Z')
            assert _relationships['parent_entity']['data']['id'] == str(obj.parent_entity.pk)
            assert _relationships['parent_entity']['data']['type'] == 'entity.parent_entity'
        elif isinstance(obj, DependentEntity):
            assert _attributes['dependent_name'] == obj.dependent_name
            assert _attributes['dependent_description'] == obj.dependent_description
            assert _attributes['dependent_is_active'] == obj.dependent_is_active
            assert _attributes['dependent_price'] == str(obj.dependent_price)
            assert _attributes[
                'dependent_dt_approved'
            ] == obj.dependent_dt_approved.isoformat().replace('+00:00', 'Z')
            assert _relationships['parent_entity']['data']['id'] == str(obj.parent_entity.pk)
            assert _relationships['parent_entity']['data']['type'] == 'entity.parent_entity'
        elif isinstance(obj, ChildEntity):
            assert _attributes['child_name'] == obj.child_name
            assert _attributes['child_description'] == obj.child_description
            assert _attributes['child_is_active'] == obj.child_is_active
            assert _attributes['child_price'] == str(obj.child_price)
            assert _attributes['child_dt_approved'] == obj.child_dt_approved.isoformat().replace(
                '+00:00', 'Z'
            )
