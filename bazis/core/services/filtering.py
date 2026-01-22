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

from urllib.parse import unquote_plus

from django.db import models
from django.db.models import QuerySet

from typing_extensions import deprecated

from bazis.core.utils.query_complex import QueryToOrm


class ServiceFiltering:
    """
    Class for applying service-level filtering to a Django QuerySet based on a URL-
    encoded filter string.

    Tags: RAG, EXPORT
    """

    def __init__(self, filter: str = ''):
        """
        Initializes the ServiceFiltering instance with a URL-encoded filter string.

        :param filter: URL-encoded filter string.
        """
        self.query_str = unquote_plus(filter)

    def apply(
        self, queryset: QuerySet, filters_aliases: dict[str, str] = None, fiter_context: dict = None
    ):
        """
        Applies the filtering to the given QuerySet using the specified filter aliases and context.

        :param queryset: The Django QuerySet to filter.
        :param filters_aliases: Optional dictionary mapping filter aliases to actual field names.
        :param fiter_context: Optional context dictionary for additional filtering logic.
        :return: Filtered QuerySet.
        """
        return QueryToOrm.qs_apply(
            queryset,
            self.query_str,
            filters_aliases=filters_aliases,
            fiter_context=fiter_context,
        )


@deprecated('Filtering is deprecated, use bazis.core.utils.query_complex.QueryToOrm instead.')
class Filtering:
    """
    Implementation of filtering for the specified queryset. Filtering is oriented towards
    the composition of the model fields from the queryset.
        Fields can be nested as much as needed, according to Django notation.

        Supported range filters:
        - gt, gte, lt, lte

        Support for special notation for full-text search:

        - '?filter=$search=text': Identical to the query '?search=text'. Full-text search across
        all text and integer fields of the model.
        - '?filter=author__$search=text': Full-text search across all text and integer fields of the
        nested 'author' model.
        - '?filter=author__username__$search=text': Full-text search only on the 'username' text field
        of the nested 'author' entity.

        For filtering non-null fields, the following suffixes are used:

        - For simple fields, the suffix 'isnull': '?filter=name__isnull=true/false'.
        - For relation fields, the suffix 'exists': '?filter=status__exists=true/false'.

    Tags: RAG, EXPORT
    """

    @classmethod
    def qs_apply(
        cls,
        queryset: QuerySet,
        query_str: str,
        filters_aliases: dict[str, str] = None,
        fiter_context: dict = None,
    ):
        return QueryToOrm.qs_apply(
            queryset,
            query_str,
            filters_aliases=filters_aliases,
            fiter_context=fiter_context,
        )

    def __init__(
        self,
        model: models.Model,
        query_str: str,
        filters_aliases: dict[str, str] = None,
        fiter_context: dict = None,
    ):
        self.model = model
        self.query_str = query_str
        self.filters_aliases = filters_aliases or {}
        self.fiter_context = fiter_context or {}

    def __call__(self):
        q_orm = QueryToOrm(self.query_str, self.model, self.filters_aliases, self.fiter_context)
        return q_orm.q, q_orm.fields_calc
