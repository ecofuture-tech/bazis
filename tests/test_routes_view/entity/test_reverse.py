from django.db import reset_queries
from django.db.backends.utils import CursorWrapper

import pytest
from bazis_test_utils.utils import get_api_client

from tests import factories


SQL_QUERIES = []


@pytest.fixture(autouse=True)
def capture_sql():
    SQL_QUERIES.clear()

    original_execute = CursorWrapper.execute

    def patched_execute(self, sql, params=None):
        SQL_QUERIES.append(sql)
        return original_execute(self, sql, params)

    CursorWrapper.execute = patched_execute
    yield
    CursorWrapper.execute = original_execute


@pytest.mark.django_db(transaction=True)
def test_reverse_list(sample_app):
    reset_queries()

    parent_entity = factories.ParentEntityFactory.create(
        name='Parent test name',
        child_entities=False,
        dependent_entities=None,
        extended_entity=None,
    )
    factories.ExtendedEntityFactory.create(
        extended_name='Extended test name', parent_entity=parent_entity
    )
    factories.DependentEntityFactory.create(
        dependent_name='Dependent test name', parent_entity=parent_entity
    )
    factories.DependentEntityFactory.create(
        dependent_name='Dependent test name 2', parent_entity=parent_entity
    )
    factories.DependentEntityFactory.create(
        dependent_name='Dependent test name 3', parent_entity=parent_entity
    )
    factories.DependentEntityFactory.create(
        dependent_name='Dependent test name 4', parent_entity=parent_entity
    )

    SQL_QUERIES.clear()

    response = get_api_client(sample_app).get(f'/api/v1/entity/parent_entity/{parent_entity.pk}/')

    assert response.status_code == 200

    assert len(SQL_QUERIES) == 1
