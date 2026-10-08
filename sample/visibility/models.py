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
Models of the tests of the route visibility of relationship targets: the route of `Tag`
hides some tags, the other models are not restricted.
"""

from django.db import models

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin


class Folder(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=255)


class Label(DtMixin, UuidMixin, JsonApiMixin):
    """A JSON:API model without a route set."""

    name = models.CharField('Name', max_length=255)


class Tag(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=255)
    is_hidden = models.BooleanField('Hidden', default=False)
    is_locked = models.BooleanField('Locked', default=False)
    note = models.ForeignKey(
        'Note', null=True, blank=True, on_delete=models.SET_NULL, related_name='attached_tags'
    )


class Note(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField('Name', max_length=255)
    folder = models.ForeignKey(
        Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name='notes'
    )
    label = models.ForeignKey(
        Label, null=True, blank=True, on_delete=models.SET_NULL, related_name='notes'
    )
    tag = models.ForeignKey(
        Tag, null=True, blank=True, on_delete=models.SET_NULL, related_name='main_notes'
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='notes')
