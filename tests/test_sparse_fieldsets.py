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
Testing that passing a list of fields for the response in query parameters works.
"""

import pytest
from bazis_test_utils.utils import get_api_client
from sparse_fieldsets.models import Article, Category, Gender, People

from tests.utils.assert_sql import assert_sql_query, get_sql_query


@pytest.mark.django_db(transaction=True)
def test_sparse_fieldsets(sample_app):
    """
    Create an author and their article, check queries to them with and without field list restrictions.
    """

    author = People.objects.create(
        name='somestring 1',
        email='somestring 2',
        gender=Gender.MALE,
    )

    category = Category.objects.create(name='somecategory', comment='no comment')

    article = Article.objects.create(
        title='somestring 3',
        body='3fa85f64-5717-4562-b3fc-2c963f66afa6',
        category=category,
    )

    article.author.add(author)

    url = f'/api/v1/sparse_fieldsets/article/{article.id}/?include=author'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    data['data']['attributes']['dt_created'] = data['data']['attributes']['dt_created'][:-8]
    data['data']['attributes']['dt_updated'] = data['data']['attributes']['dt_updated'][:-8]
    data['included'][0]['attributes']['dt_created'] = data['included'][0]['attributes'][
        'dt_created'
    ][:-8]
    data['included'][0]['attributes']['dt_updated'] = data['included'][0]['attributes'][
        'dt_updated'
    ][:-8]
    assert data == {
        'data': {
            'attributes': {
                'author_count': 1,
                'author_detail': [{'child_name': 'somestring 1', 'id': str(author.id)}],
                'body': '3fa85f64-5717-4562-b3fc-2c963f66afa6',
                'dt_created': article.dt_created.strftime('%Y-%m-%dT%H:%M:%S'),
                'dt_updated': article.dt_updated.strftime('%Y-%m-%dT%H:%M:%S'),
                'some_count_property': 1000,
                'title': 'somestring 3',
            },
            'bs:action': 'view',
            'id': str(article.id),
            'relationships': {
                'author': {'data': [{'id': str(author.id), 'type': 'sparse_fieldsets.people'}]},
                'category': {'data': {'id': str(category.id), 'type': 'sparse_fieldsets.category'}},
            },
            'type': 'sparse_fieldsets.article',
        },
        'included': [
            {
                'attributes': {
                    'dt_created': author.dt_created.strftime('%Y-%m-%dT%H:%M:%S'),
                    'dt_updated': author.dt_updated.strftime('%Y-%m-%dT%H:%M:%S'),
                    'email': 'somestring 2',
                    'gender': 'm',
                    'name': 'somestring 1',
                },
                'bs:action': 'view',
                'id': str(author.id),
                'relationships': {
                    'articles': {
                        'data': [{'id': str(article.id), 'type': 'sparse_fieldsets.article'}]
                    }
                },
                'type': 'sparse_fieldsets.people',
            }
        ],
        'meta': {},
    }

    # the query includes all fields of the main model and all fields of included models, including calculated fields and relationships
    sql_query1, sql_query2 = get_sql_query([-2, -1])
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."dt_created",
               "sparse_fieldsets_article"."dt_updated",
               "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title",
               "sparse_fieldsets_article"."body",
               "sparse_fieldsets_article"."category_id",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'sparse_fieldsets.people') AS "json"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author__ids",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('name')::text, V0."name") AS "json"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "_author",
        
          (SELECT Count(V0."id") AS "_resp"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author_count"
        FROM "sparse_fieldsets_article"
        WHERE "sparse_fieldsets_article"."id" = 'id_hex'::UUID
        ORDER BY "sparse_fieldsets_article"."id" ASC
        LIMIT 1;
    """
    assert_sql_query(expected_sql_template, sql_query1, article.id.hex)
    expected_sql_template = """
        SELECT "sparse_fieldsets_people"."dt_created",
               "sparse_fieldsets_people"."dt_updated",
               "sparse_fieldsets_people"."id",
               "sparse_fieldsets_people"."name",
               "sparse_fieldsets_people"."email",
               "sparse_fieldsets_people"."gender",
               EXISTS
          (SELECT 1 AS "a"
           FROM "sparse_fieldsets_article_author" U0
           WHERE (U0."article_id" = 'id_hex'::UUID
                  AND U0."people_id" = ("sparse_fieldsets_people"."id"))
           LIMIT 1) AS "_is_exist",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'sparse_fieldsets.article') AS "json"
           FROM "sparse_fieldsets_article" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = (V0."id")
                       AND U0."people_id" = ("sparse_fieldsets_people"."id"))
                LIMIT 1)) AS "articles__ids"
        FROM "sparse_fieldsets_people"
        WHERE EXISTS
            (SELECT 1 AS "a"
             FROM "sparse_fieldsets_article_author" U0
             WHERE (U0."article_id" = 'id_hex'::UUID
                    AND U0."people_id" = ("sparse_fieldsets_people"."id"))
             LIMIT 1)
    """
    assert_sql_query(expected_sql_template, sql_query2, article.id.hex)

    # Pass a list of main model fields, including calculated fields, relationships, and property fields.
    # Check that all other main model fields are excluded, including fields that are relationships.
    url = '/api/v1/sparse_fieldsets/article/?fields[sparse_fieldsets.article]=title,author,author_count,some_count_property'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    assert data == {
        'data': [
            {
                'attributes': {
                    'author_count': 1,
                    'some_count_property': 1000,
                    'title': 'somestring 3',
                },
                'bs:action': 'view',
                'id': str(article.id),
                'relationships': {
                    'author': {'data': [{'id': str(author.id), 'type': 'sparse_fieldsets.people'}]}
                },
                'type': 'sparse_fieldsets.article',
            }
        ],
        'links': {
            'first': 'http://testserver/api/v1/sparse_fieldsets/article/?fields%5Bsparse_fieldsets.article%5D=title%2Cauthor%2Cauthor_count%2Csome_count_property',
            'last': 'http://testserver/api/v1/sparse_fieldsets/article/?fields%5Bsparse_fieldsets.article%5D=title%2Cauthor%2Cauthor_count%2Csome_count_property&page%5Blimit%5D=20&page%5Boffset%5D=0',
            'next': None,
            'prev': None,
        },
        'meta': {},
    }

    # the query only includes the title field, the calculated field author_count, and the relationship field author (plus the mandatory id field)
    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title",
               ARRAY
          (SELECT JSONB_BUILD_OBJECT(('id')::text, V0."id", ('_jsonapi_type')::text, 'sparse_fieldsets.people') AS "json"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author__ids",
        
          (SELECT Count(V0."id") AS "_resp"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author_count"
        FROM "sparse_fieldsets_article"
        LIMIT 20;
    """
    assert_sql_query(expected_sql_template, sql_query)

    # Pass a list of main model fields, including calculated fields, but without relationships.
    # Check that all other main model fields are excluded from the list query response,
    # including fields that are relationships.
    url = '/api/v1/sparse_fieldsets/article/?fields[sparse_fieldsets.article]=title,author_count'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    assert data == {
        'data': [
            {
                'attributes': {'author_count': 1, 'title': 'somestring 3'},
                'bs:action': 'view',
                'id': str(article.id),
                'relationships': {},
                'type': 'sparse_fieldsets.article',
            }
        ],
        'links': {
            'first': 'http://testserver/api/v1/sparse_fieldsets/article/?fields%5Bsparse_fieldsets.article%5D=title%2Cauthor_count',
            'last': 'http://testserver/api/v1/sparse_fieldsets/article/?fields%5Bsparse_fieldsets.article%5D=title%2Cauthor_count&page%5Blimit%5D=20&page%5Boffset%5D=0',
            'next': None,
            'prev': None,
        },
        'meta': {},
    }

    # the query only includes the title field and the calculated field author_count (plus the mandatory id field)
    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title",
          (SELECT Count(V0."id") AS "_resp"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author_count"
        FROM "sparse_fieldsets_article"
        LIMIT 20;
    """
    assert_sql_query(expected_sql_template, sql_query)

    # Now check for a query to get a single item, not a list.
    url = f'/api/v1/sparse_fieldsets/article/{article.id}/?fields[sparse_fieldsets.article]=title,dt_created,author_count'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    data['data']['attributes']['dt_created'] = data['data']['attributes']['dt_created'][:-8]
    assert data == {
        'data': {
            'attributes': {
                'author_count': 1,
                'dt_created': article.dt_created.strftime('%Y-%m-%dT%H:%M:%S'),
                'title': 'somestring 3',
            },
            'bs:action': 'view',
            'id': str(article.id),
            'relationships': {},
            'type': 'sparse_fieldsets.article',
        },
        'meta': {},
    }

    # the query only includes the title, dt_created fields and the calculated field author_count (plus the mandatory id field)
    sql_query = get_sql_query()
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."dt_created",
               "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title",       
          (SELECT Count(V0."id") AS "_resp"
           FROM "sparse_fieldsets_people" V0
           WHERE EXISTS
               (SELECT 1 AS "a"
                FROM "sparse_fieldsets_article_author" U0
                WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                       AND U0."people_id" = (V0."id"))
                LIMIT 1)) AS "author_count"
        FROM "sparse_fieldsets_article"
        WHERE "sparse_fieldsets_article"."id" = 'id_hex'::UUID
        ORDER BY "sparse_fieldsets_article"."id" ASC
        LIMIT 1;
    """
    assert_sql_query(expected_sql_template, sql_query, article.id.hex)

    # In addition to the main model field list, pass a list of related model fields, included via include.
    url = f'/api/v1/sparse_fieldsets/article/{article.id}/?fields[sparse_fieldsets.article]=title&include=author&fields[sparse_fieldsets.people]=name,email'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    assert data == {
        'data': {
            'attributes': {'title': 'somestring 3'},
            'bs:action': 'view',
            'id': str(article.id),
            'relationships': {},
            'type': 'sparse_fieldsets.article',
        },
        'included': [
            {
                'attributes': {'email': 'somestring 2', 'name': 'somestring 1'},
                'bs:action': 'view',
                'id': str(author.id),
                'relationships': {},
                'type': 'sparse_fieldsets.people',
            }
        ],
        'meta': {},
    }

    # the query for the main model only includes the title field for article, the query for the included people table only includes name and email (plus the mandatory id field)
    sql_query1, sql_query2 = get_sql_query([-2, -1])
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title"
        FROM "sparse_fieldsets_article"
        WHERE "sparse_fieldsets_article"."id" = 'id_hex'::UUID
        ORDER BY "sparse_fieldsets_article"."id" ASC
        LIMIT 1;
    """
    assert_sql_query(expected_sql_template, sql_query1, article.id.hex)
    expected_sql_template = """
        SELECT "sparse_fieldsets_people"."id",
               "sparse_fieldsets_people"."name",
               "sparse_fieldsets_people"."email",
               EXISTS
          (SELECT 1 AS "a"
           FROM "sparse_fieldsets_article_author" U0
           WHERE (U0."article_id" = 'id_hex'::UUID
                  AND U0."people_id" = ("sparse_fieldsets_people"."id"))
           LIMIT 1) AS "_is_exist"
        FROM "sparse_fieldsets_people"
        WHERE EXISTS
            (SELECT 1 AS "a"
             FROM "sparse_fieldsets_article_author" U0
             WHERE (U0."article_id" = 'id_hex'::UUID
                    AND U0."people_id" = ("sparse_fieldsets_people"."id"))
             LIMIT 1)
    """
    assert_sql_query(expected_sql_template, sql_query2, article.id.hex)

    # Check field restriction for two related models.
    url = f'/api/v1/sparse_fieldsets/article/{article.id}/?fields[sparse_fieldsets.article]=title&include=author,category&fields[sparse_fieldsets.people]=name&fields[sparse_fieldsets.category]=name'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    assert data == {
        'data': {
            'attributes': {'title': 'somestring 3'},
            'bs:action': 'view',
            'id': str(article.id),
            'relationships': {},
            'type': 'sparse_fieldsets.article',
        },
        'included': [
            {
                'attributes': {'name': 'somecategory'},
                'bs:action': 'view',
                'id': str(category.id),
                'relationships': {},
                'type': 'sparse_fieldsets.category',
            },
            {
                'attributes': {'name': 'somestring 1'},
                'bs:action': 'view',
                'id': str(author.id),
                'relationships': {},
                'type': 'sparse_fieldsets.people',
            },
        ],
        'meta': {},
    }

    # the query for the main model only includes the title field for article, the queries for included tables only include name (plus the mandatory id field)
    sql_query1, sql_query2, sql_query3 = get_sql_query([-3, -2, -1])
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title"
        FROM "sparse_fieldsets_article"
        WHERE "sparse_fieldsets_article"."id" = 'id_hex'::UUID
        ORDER BY "sparse_fieldsets_article"."id" ASC
        LIMIT 1;
    """
    assert_sql_query(expected_sql_template, sql_query1, article.id.hex)
    expected_sql_template = """
        SELECT "sparse_fieldsets_category"."id",
               "sparse_fieldsets_category"."name"
        FROM "sparse_fieldsets_category"
        INNER JOIN "sparse_fieldsets_article" ON ("sparse_fieldsets_category"."id" = "sparse_fieldsets_article"."category_id")
        WHERE "sparse_fieldsets_article"."id" = 'id_hex'::UUID
    """
    assert_sql_query(expected_sql_template, sql_query2, article.id.hex)
    expected_sql_template = """
        SELECT "sparse_fieldsets_people"."id",
               "sparse_fieldsets_people"."name",
               EXISTS
          (SELECT 1 AS "a"
           FROM "sparse_fieldsets_article_author" U0
           WHERE (U0."article_id" = 'id_hex'::UUID
                  AND U0."people_id" = ("sparse_fieldsets_people"."id"))
           LIMIT 1) AS "_is_exist"
        FROM "sparse_fieldsets_people"
        WHERE EXISTS
            (SELECT 1 AS "a"
             FROM "sparse_fieldsets_article_author" U0
             WHERE (U0."article_id" = 'id_hex'::UUID
                    AND U0."people_id" = ("sparse_fieldsets_people"."id"))
             LIMIT 1)
    """
    assert_sql_query(expected_sql_template, sql_query3, article.id.hex)

    # Check the mechanism for reverse queries from author to article.
    url = f'/api/v1/sparse_fieldsets/people/{author.id}/?fields[sparse_fieldsets.people]=name,email&include=articles&fields[sparse_fieldsets.article]=title'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200
    data = response.json()
    assert data == {
        'data': {
            'attributes': {'email': 'somestring 2', 'name': 'somestring 1'},
            'bs:action': 'view',
            'id': str(author.id),
            'relationships': {},
            'type': 'sparse_fieldsets.people',
        },
        'included': [
            {
                'attributes': {'title': 'somestring 3'},
                'bs:action': 'view',
                'id': str(article.id),
                'relationships': {},
                'type': 'sparse_fieldsets.article',
            }
        ],
        'meta': {},
    }

    # the query for the main model only includes the name and email fields for people, the query for included articles only includes title (plus the mandatory id field)
    sql_query1, sql_query2 = get_sql_query([-2, -1])
    expected_sql_template = """
        SELECT "sparse_fieldsets_people"."id",
               "sparse_fieldsets_people"."name",
               "sparse_fieldsets_people"."email"
        FROM "sparse_fieldsets_people"
        WHERE "sparse_fieldsets_people"."id" = 'id_hex'::UUID
        ORDER BY "sparse_fieldsets_people"."id" ASC
        LIMIT 1;
    """
    assert_sql_query(expected_sql_template, sql_query1, author.id.hex)
    expected_sql_template = """
        SELECT "sparse_fieldsets_article"."id",
               "sparse_fieldsets_article"."title",
               EXISTS
          (SELECT 1 AS "a"
           FROM "sparse_fieldsets_article_author" U0
           WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                  AND U0."people_id" = 'id_hex'::UUID)
           LIMIT 1) AS "_is_exist"
        FROM "sparse_fieldsets_article"
        WHERE EXISTS
            (SELECT 1 AS "a"
             FROM "sparse_fieldsets_article_author" U0
             WHERE (U0."article_id" = ("sparse_fieldsets_article"."id")
                    AND U0."people_id" = 'id_hex'::UUID)
             LIMIT 1)
    """
    assert_sql_query(expected_sql_template, sql_query2, author.id.hex)
