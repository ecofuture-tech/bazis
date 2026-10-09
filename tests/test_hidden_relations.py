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
Relations without a reverse one (`related_name='+'`). `included` of a forward relation
queried the related objects by the name of the reverse relation, which is `+` for all of
them: Django took the hidden reverse relation of another model, so the included objects
were those of another item with the same key (integer keys) or none. The filter by the
objects of a model (`catalog.memo=<id>`) had the same defect.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Attachment, Card, Memo

from bazis.core.utils.model_meta import FieldsInfo
from bazis.core.utils.query_complex import QueryToOrm


MEMOS = '/api/v1/catalog/memo/'
CARDS = '/api/v1/catalog/card/'


def included(response):
    assert response.status_code == 200, response.text
    return sorted((it['type'], str(it['id'])) for it in response.json().get('included', []))


def attachments(*objs):
    return sorted(('catalog.attachment', str(it.pk)) for it in objs)


@pytest.fixture
def same_keys(db):
    """A memo and a card with the same key, each with attachments of its own."""
    files = {
        name: Attachment.objects.create(name=name) for name in ('memo', 'cover', 'extra', 'card')
    }
    memo = Memo.objects.create(pk=101, title='memo', attachment=files['memo'], cover=files['cover'])
    memo.extras.add(files['extra'])
    card = Card.objects.create(pk=101, name='card', attachment=files['card'])
    return memo, card, files


@pytest.mark.django_db(transaction=True)
def test_included_relations_without_reverse(sample_app, same_keys):
    memo, card, files = same_keys
    client = get_api_client(sample_app)

    # a foreign key, a one-to-one relation and a many-to-many relation
    assert included(client.get(f'{MEMOS}{memo.pk}/?include=attachment')) == attachments(
        files['memo']
    )
    assert included(client.get(f'{MEMOS}{memo.pk}/?include=cover')) == attachments(files['cover'])
    assert included(client.get(f'{MEMOS}{memo.pk}/?include=extras')) == attachments(files['extra'])
    assert included(client.get(f'{CARDS}{card.pk}/?include=attachment')) == attachments(
        files['card']
    )


@pytest.mark.django_db(transaction=True)
def test_included_relation_without_reverse_is_its_own(sample_app, same_keys):
    """An item without the relation includes nothing, not the object of another item."""
    memo, card, files = same_keys
    other = Memo.objects.create(pk=card.pk + 1, title='other')
    Card.objects.create(pk=other.pk, name='other', attachment=files['card'])

    assert included(get_api_client(sample_app).get(f'{MEMOS}{other.pk}/?include=attachment')) == []


@pytest.mark.django_db(transaction=True)
def test_child_queryset_of_forward_relations(same_keys):
    """Each kind of a forward relation queries the objects of the item itself."""
    memo, card, files = same_keys
    relations = FieldsInfo.get_fields_info(Memo).relations

    for name, expected in (('attachment', 'memo'), ('cover', 'cover'), ('extras', 'extra')):
        with CaptureQueriesContext(connection) as queries:
            assert list(relations[name].get_child_queryset(memo.pk)) == [files[expected]]
        # never through the tables of the cards
        assert all('catalog_card' not in it['sql'] for it in queries.captured_queries)

    card_relations = FieldsInfo.get_fields_info(Card).relations
    assert list(card_relations['attachment'].get_child_queryset(card.pk)) == [files['card']]
    assert list(card_relations['memo'].get_child_queryset(card.pk)) == []


@pytest.mark.django_db(transaction=True)
def test_filter_by_objects_skips_relations_without_reverse(same_keys):
    """
    `catalog.card=<id>` on the attachments: the foreign key of the cards to them has no
    reverse relation to filter the attachments by (its name `+` names a hidden relation of
    any model), so the model is not related for the filter. A many-to-many relation without
    a reverse one has a hidden name of its own and filters: `catalog.memo=<id>` gives the
    extras of the memo, not its attachment and cover (foreign keys without a reverse one).
    """
    memo, card, files = same_keys

    with pytest.raises(ValueError, match='not a model related'):
        QueryToOrm.qs_apply(Attachment.objects.all(), f'catalog.card={card.pk}', scope=None)

    attachments_of_memo = QueryToOrm.qs_apply(
        Attachment.objects.all(), f'catalog.memo={memo.pk}', scope=None
    )
    assert list(attachments_of_memo) == [files['extra']]

    # a relation with a reverse one still filters
    cards = QueryToOrm.qs_apply(Card.objects.all(), f'catalog.memo={memo.pk}', scope=None)
    assert list(cards) == []
    card.memo = memo
    card.save()
    cards = QueryToOrm.qs_apply(Card.objects.all(), f'catalog.memo={memo.pk}', scope=None)
    assert list(cards) == [card]


@pytest.mark.django_db(transaction=True)
def test_count_of_a_model_with_ordering(sample_app):
    """
    `FieldDynamic(func='Count')` over a model with `Meta.ordering`: the ordering of the
    subquery made it invalid (the ordered column is not grouped).
    """
    memo = Memo.objects.create(title='memo')
    Card.objects.create(name='b', memo=memo)
    Card.objects.create(name='a', memo=memo)
    empty = Memo.objects.create(title='empty')
    client = get_api_client(sample_app)

    response = client.get(f'{MEMOS}{memo.pk}/')
    assert response.status_code == 200, response.text
    assert response.json()['data']['attributes']['cards_count'] == 2

    response = client.get(f'{MEMOS}?sort=id')
    assert response.status_code == 200, response.text
    counts = {str(it['id']): it['attributes']['cards_count'] for it in response.json()['data']}
    assert counts == {str(memo.pk): 2, str(empty.pk): 0}
