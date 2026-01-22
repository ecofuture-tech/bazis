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

from django.core.exceptions import FieldError
from django.db.models import F, QuerySet
from django.utils.translation import gettext as _

from bazis.core.errors import JsonApiBazisError, JsonApiBazisException
from bazis.core.routes_abstract.initial import InitialRouteBase


class SortingSearching:
    """
    Class responsible for handling sorting and searching operations on querysets.

    Tags: RAG, EXPORT
    """

    terms: list[str]
    route_cls: type[InitialRouteBase]

    def __init__(self, sort: str = None):
        """
        Initializes the SortingSearching instance with sorting terms parsed from a
        comma-separated string.
        """
        self.terms = []
        if sort:
            self.terms = [it.strip() for it in sort.split(',') if it.strip()]

    def apply(self, queryset: QuerySet):
        """
        Applies the sorting terms to the given queryset. Raises a JsonApiBazisException
        if the sorting parameters are invalid.
        """
        if not self.terms:
            return queryset
        try:
            return queryset.order_by(
                *[F(t[1:]).desc(nulls_last=True) if t.startswith('-') else t for t in self.terms]
            )
        except FieldError:
            raise JsonApiBazisException(
                JsonApiBazisError(
                    detail=_('Invalid sorting parameters: `%s`') % self.terms, loc=('path', 'sort')
                ),
            ) from None
