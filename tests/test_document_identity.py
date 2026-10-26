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
The resource of the document of a create or an update is the resource of the route: a
`type` of another model, or an update `id` that is not the id of the path, is 409
`ERR_RESOURCE_MISMATCH` and nothing is written. Up to 2.23 the `type` was not checked (a
create took the model to create from it: a POST to the route of one model created an
object of another one, or failed with 500) and the `id` of an update was ignored.
"""

import uuid

import pytest
from bazis_test_utils.utils import get_api_client
from catalog.models import Attachment, BusyMemo, Memo, Upload
from catalog.routes import AttachmentRouteSet, MemoRouteSet
from entity.models import Country

from bazis.core.schemas.enums import CrudApiAction


ATTACHMENTS = '/api/v1/catalog/attachment/'
MEMOS = '/api/v1/catalog/memo/'
COUNTRIES = '/api/v1/entity/country/'


def document(type_=None, id_=None, **attributes):
    data = {'attributes': attributes}
    if type_ is not None:
        data['type'] = type_
    if id_ is not None:
        data['id'] = id_
    return {'data': data}


def mismatch_pointers(response):
    """The pointers of the errors of a 409 `ERR_RESOURCE_MISMATCH`, in their order."""
    assert response.status_code == 409, response.text
    errors = response.json()['errors']
    assert {(it['status'], it['code'], it['title']) for it in errors} == {
        (409, 'ERR_RESOURCE_MISMATCH', 'Resource mismatch')
    }, errors
    return [it['source']['pointer'] for it in errors]


@pytest.fixture
def writes(monkeypatch):
    """
    The writes of the route of the attachments and their hooks, by name, in their order
    (none on a mismatch).
    """
    called = []
    for name in ('item_create', 'hook_before_create', 'item_update', 'hook_before_update'):
        method = getattr(AttachmentRouteSet, name)

        def spy(self, *args, _name=name, _method=method, **kwargs):
            called.append(_name)
            return _method(self, *args, **kwargs)

        monkeypatch.setattr(AttachmentRouteSet, name, spy)
    return called


@pytest.fixture
def memos_of_a_child_model(monkeypatch):
    """The route of the memos shows them as instances of a model that inherits Memo."""
    monkeypatch.setattr(MemoRouteSet, 'get_queryset', lambda self: BusyMemo.objects.all())


@pytest.mark.django_db(transaction=True)
def test_create_with_the_type_of_another_model(sample_app, writes):
    """
    The type of another model whose attributes have the same names created an object of
    that model through the route (201 with the attachment of the same id, if any).
    """
    Attachment.objects.create(name='existing')

    response = get_api_client(sample_app).post(
        ATTACHMENTS, json_data=document('catalog.upload', name='made-via-attachment-route')
    )

    assert mismatch_pointers(response) == ['/data/type']
    assert response.json()['errors'][0]['detail'] == (
        'The type catalog.upload of the document is not the type catalog.attachment of the route'
    )
    assert not Upload.objects.exists()
    assert list(Attachment.objects.values_list('name', flat=True)) == ['existing']
    # refused before the item is built: no hook of the create runs
    assert writes == []


@pytest.mark.django_db(transaction=True)
def test_create_with_the_type_of_a_child_model(sample_app):
    """The type of a model that inherits the model of the route is another type."""
    response = get_api_client(sample_app).post(
        MEMOS, json_data=document('catalog.busy_memo', title='busy-via-memo-route')
    )

    assert mismatch_pointers(response) == ['/data/type']
    assert not Memo.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'type_',
    [
        'nope.nothing',  # no such model: was a 500
        '',  # was a 500
        'catalog.memo',  # a model without the attributes of the route: was a 500
        'auth.group',  # a model that is not a resource: was a 500
        'catalog.Attachment',  # the label is exact
    ],
)
def test_create_with_a_type_that_is_not_the_route(sample_app, type_):
    response = get_api_client(sample_app).post(ATTACHMENTS, json_data=document(type_, name='x'))

    assert mismatch_pointers(response) == ['/data/type']
    assert not Attachment.objects.exists()


def test_the_model_of_a_write_is_the_model_of_the_schema(sample_app):
    """`build_for` builds the model of the schema, whatever the `type` of the data says."""
    schema = AttachmentRouteSet.schema_defaults[CrudApiAction.CREATE]
    data = schema.model_validate(document('catalog.upload', name='x')).data

    assert type(data.build_for()) is Attachment


@pytest.mark.django_db(transaction=True)
def test_update_with_the_type_of_another_model(sample_app, writes):
    attachment = Attachment.objects.create(name='A')

    response = get_api_client(sample_app).patch(
        f'{ATTACHMENTS}{attachment.pk}/',
        json_data=document('catalog.upload', attachment.pk, name='A-renamed-by-foreign-type'),
    )

    assert mismatch_pointers(response) == ['/data/type']
    attachment.refresh_from_db()
    assert attachment.name == 'A'
    # refused before the write: no hook of the update runs
    assert writes == []


@pytest.mark.django_db(transaction=True)
def test_update_with_the_id_of_another_object(sample_app, writes):
    """The id of another object was ignored: the object of the path was changed."""
    first, second = Attachment.objects.create(name='A'), Attachment.objects.create(name='B')

    response = get_api_client(sample_app).patch(
        f'{ATTACHMENTS}{first.pk}/',
        json_data=document('catalog.attachment', second.pk, name='written-with-id-of-B'),
    )

    assert mismatch_pointers(response) == ['/data/id']
    assert response.json()['errors'][0]['detail'] == (
        'The id of the document is not the id of the path'
    )
    assert sorted(Attachment.objects.values_list('name', flat=True)) == ['A', 'B']
    assert writes == []


@pytest.mark.django_db(transaction=True)
def test_update_with_another_type_and_id(sample_app, writes):
    """Both mismatches are answered at once, the type first."""
    first, second = Attachment.objects.create(name='A'), Attachment.objects.create(name='B')

    response = get_api_client(sample_app).patch(
        f'{ATTACHMENTS}{first.pk}/', json_data=document('catalog.upload', second.pk, name='C')
    )

    assert mismatch_pointers(response) == ['/data/type', '/data/id']
    assert sorted(Attachment.objects.values_list('name', flat=True)) == ['A', 'B']
    assert writes == []


@pytest.mark.django_db(transaction=True)
def test_documents_of_the_route(sample_app):
    """Without `type` the schema gives the type of the route; the id of a create is free."""
    client = get_api_client(sample_app)

    response = client.post(ATTACHMENTS, json_data=document(name='no type'))
    assert response.status_code == 201, response.text
    attachment = Attachment.objects.get(name='no type')

    response = client.patch(
        f'{ATTACHMENTS}{attachment.pk}/', json_data=document(id_=attachment.pk, name='renamed')
    )
    assert response.status_code == 200, response.text

    # the id of a create is the id of the client
    response = client.post(ATTACHMENTS, json_data=document('catalog.attachment', 777, name='777'))
    assert response.status_code == 201, response.text
    assert Attachment.objects.get(pk=777).name == '777'

    # the ids are compared as keys of the model, typed by the schema
    response = client.patch(
        f'{ATTACHMENTS}777/', json_data=document('catalog.attachment', ' 777', name='spaced')
    )
    assert response.status_code == 200, response.text
    assert sorted(Attachment.objects.values_list('name', flat=True)) == ['renamed', 'spaced']


@pytest.mark.django_db(transaction=True)
def test_update_with_a_uuid_in_upper_case(sample_app):
    country = Country.objects.create(name='Norway')
    upper = str(country.pk).upper()

    response = get_api_client(sample_app).patch(
        f'{COUNTRIES}{upper}/', json_data=document('entity.country', upper, name='Sweden')
    )

    assert response.status_code == 200, response.text
    country.refresh_from_db()
    assert country.name == 'Sweden'

    # another key is another object
    response = get_api_client(sample_app).patch(
        f'{COUNTRIES}{country.pk}/', json_data=document('entity.country', str(uuid.uuid4()))
    )
    assert mismatch_pointers(response) == ['/data/id']


@pytest.mark.django_db(transaction=True)
def test_update_without_id(sample_app):
    """The id of an update stays required by its schema (422, not 409)."""
    attachment = Attachment.objects.create(name='A')

    response = get_api_client(sample_app).patch(
        f'{ATTACHMENTS}{attachment.pk}/', json_data=document('catalog.upload', name='B')
    )

    assert response.status_code == 422, response.text
    (error,) = response.json()['errors']
    assert (error['code'], error['source']['pointer']) == ('ERR_VALIDATE', '/data/id')
    attachment.refresh_from_db()
    assert attachment.name == 'A'


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('type_', [None, 'catalog.busy_memo', 'catalog.memo'])
def test_update_on_a_route_of_the_instances_of_a_child_model(
    sample_app, memos_of_a_child_model, type_
):
    """
    A route whose queryset gives the instances of a child model shows them with the type
    of that model: an update takes it, the type of the route, or none.
    """
    memo = Memo.objects.create(title='memo')

    response = get_api_client(sample_app).patch(
        f'{MEMOS}{memo.pk}/', json_data=document(type_, memo.pk, title='new')
    )

    assert response.status_code == 200, response.text
    assert response.json()['data']['type'] == 'catalog.busy_memo'
    memo.refresh_from_db()
    assert memo.title == 'new'


@pytest.mark.django_db(transaction=True)
def test_other_types_on_a_route_of_the_instances_of_a_child_model(
    sample_app, memos_of_a_child_model
):
    """Another type is refused on an update, the type of the child model on a create."""
    memo = Memo.objects.create(title='memo')
    client = get_api_client(sample_app)

    response = client.patch(
        f'{MEMOS}{memo.pk}/', json_data=document('catalog.attachment', memo.pk, title='new')
    )
    assert mismatch_pointers(response) == ['/data/type']
    memo.refresh_from_db()
    assert memo.title == 'memo'

    response = client.post(MEMOS, json_data=document('catalog.busy_memo', title='busy'))
    assert mismatch_pointers(response) == ['/data/type']
    assert list(Memo.objects.values_list('title', flat=True)) == ['memo']
