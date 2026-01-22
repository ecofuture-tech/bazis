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

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.core.utils.functools import get_attr

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_routes_delete(sample_app):
    parent_entity = factories.ParentEntityFactory.create(
        name='Parent test name',
        child_entities=False,
        dependent_entities=None,
        extended_entity=None,
    )
    extended_entity = factories.ExtendedEntityFactory.create(
        extended_name='Extended test name', parent_entity=parent_entity
    )
    dependent_entity_1 = factories.DependentEntityFactory.create(
        dependent_name='Dependent test name', parent_entity=parent_entity
    )
    dependent_entity_2 = factories.DependentEntityFactory.create(
        dependent_name='Dependent test name 2', parent_entity=parent_entity
    )
    child_entity_1 = factories.ChildEntityFactory.create(
        child_name='Child test name',
    )
    child_entity_2 = factories.ChildEntityFactory.create(
        child_name='Child test name 2',
    )
    child_entity_3 = factories.ChildEntityFactory.create(
        child_name='Child test name 3',
    )
    parent_entity.child_entities.add(child_entity_1)
    parent_entity.child_entities.add(child_entity_2)
    parent_entity.child_entities.add(child_entity_3)

    # delete extended_entity
    assert parent_entity.extended_entity == extended_entity

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/extended_entity/{extended_entity.pk}/'
    )

    assert response.status_code == 204
    parent_entity.refresh_from_db()
    assert get_attr(parent_entity, 'extended_entity') is None

    # delete dependent_entity
    assert parent_entity.dependent_entities.exists()
    assert parent_entity.dependent_entities.count() == 2

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/dependent_entity/{dependent_entity_1.pk}/'
    )

    assert response.status_code == 204
    parent_entity.refresh_from_db()
    assert parent_entity.dependent_entities.count() == 1

    # delete child_entity
    assert parent_entity.child_entities.exists()
    assert parent_entity.child_entities.count() == 3

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/child_entity/{child_entity_1.pk}/'
    )

    assert response.status_code == 204
    parent_entity.refresh_from_db()
    assert parent_entity.child_entities.count() == 2

    # delete parent_entity
    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/parent_entity/{parent_entity.pk}/'
    )

    assert response.status_code == 204

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/{parent_entity.pk}/')
    assert response.status_code == 404

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/extended_entity/{extended_entity.pk}/'
    )
    assert response.status_code == 404

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/dependent_entity/{dependent_entity_1.pk}/'
    )
    assert response.status_code == 404

    response = get_api_client(sample_app).get(
        f'/api/v1/entity/dependent_entity/{dependent_entity_2.pk}/'
    )
    assert response.status_code == 404

    response = get_api_client(sample_app).get(f'/api/v1/entity/child_entity/{child_entity_1.pk}/')
    assert response.status_code == 404

    response = get_api_client(sample_app).get(f'/api/v1/entity/child_entity/{child_entity_2.pk}/')
    assert response.status_code == 200

    response = get_api_client(sample_app).get(f'/api/v1/entity/child_entity/{child_entity_3.pk}/')
    assert response.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_routes_delete_protected(sample_app):
    child_entity_1 = factories.ChildEntityFactory.create(
        child_name='Child test name',
    )

    with_protected_entity_1 = factories.WithProtectedEntityFactory.create(
        child=child_entity_1,
    )

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/child_entity/{child_entity_1.pk}/'
    )

    assert response.json() == {
        'errors': [
            {
                'status': 422,
                'title': 'Error deleting protected model',
                'code': 'MODEL_PROTECTED_RELATION',
                'detail': 'Cannot delete object because it has protected related objects of type entity.with_protected_entity (count: 1)',
                'meta': {'type': 'entity.with_protected_entity', 'count': 1},
            }
        ]
    }

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/with_protected_entity/{with_protected_entity_1.pk}/'
    )
    assert response.status_code == 204

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/child_entity/{child_entity_1.pk}/'
    )
    assert response.status_code == 204


@pytest.mark.django_db(transaction=True)
def test_routes_delete_protected_system(sample_app):
    child_entity_1 = factories.ChildEntityFactory.create(
        child_name='Child test name',
    )

    factories.WithProtectedEntitySystemFactory.create(
        child=child_entity_1,
    )

    response = get_api_client(sample_app).delete(
        f'/api/v1/entity/child_entity/{child_entity_1.pk}/'
    )

    assert response.json() == {
        'errors': [
            {
                'status': 422,
                'title': 'entity.WithProtectedEntitySystem is not JSON:API compliant',
                'code': 'MODEL_NOT_JSONAPI',
                'detail': 'Cannot delete object because it has related objects in non-JSON:API models. (count: 1)',
                'meta': {'type': 'entity.WithProtectedEntitySystem', 'count': 1},
            }
        ]
    }
