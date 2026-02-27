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

from django.db import models
from django.utils.functional import cached_property

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin
from bazis.core.utils.orm import (
    FieldJson,
    FieldSubAggr,
    calc_property,
)


class Gender(models.TextChoices):
    MALE = (
        'm',
        'Male',
    )
    FEMALE = (
        'f',
        'Female',
    )


class People(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField(max_length=255)
    email = models.CharField(
        'Email',
        max_length=255,
    )
    gender = models.CharField(
        'State',
        max_length=1,
        choices=Gender,
    )


class Category(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField(max_length=255)
    comment = models.CharField(max_length=255)


class Article(DtMixin, UuidMixin, JsonApiMixin):
    author = models.ManyToManyField(
        People,
        related_name='articles',
        blank=True,
    )
    title = models.CharField(
        'Title',
        max_length=25,
    )
    body = models.CharField(
        'Title',
        max_length=250,
    )
    category = models.ForeignKey(
        'Category', on_delete=models.CASCADE, related_name='articles', null=True
    )

    @calc_property(
        [
            FieldJson(
                source='author',
                fields=[
                    'id',
                    'name',
                ],
            ),
        ]
    )
    def author_detail(self) -> list:
        return [
            {
                'id': author['id'],
                'child_name': author['name'],
            }
            for author in self._author
        ]

    @calc_property(
        [
            FieldSubAggr(
                'author',
                func='Count',
                alias='author_count',
            ),
        ]
    )
    def author_count(self) -> int:
        return self.author_count

    @property
    def some_count_property(self) -> int:
        return 1000

    @cached_property
    def some_cached_property(self) -> int:
        return 2000
