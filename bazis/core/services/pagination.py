from django.conf import settings
from django.db.models import QuerySet
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from fastapi import Query, Request

from pydantic import BaseModel

from bazis.core.schemas.enums import CrudApiAction
from bazis.core.schemas.meta import meta_field
from bazis.core.schemas.schemas import PaginationLinks


class PaginationMeta(BaseModel):
    """
    Represents the metadata for pagination, including count, limit, and offset.

    Tags: RAG, EXPORT
    """

    count: int
    limit: int
    offset: int


class ServicePagination:
    """
    Handles pagination logic for a given request, including calculating offsets,
    limits, and generating pagination links.

    Tags: RAG, EXPORT
    """

    param_offset: str = 'page[offset]'
    param_limit: str = 'page[limit]'

    def __init__(
        self,
        request: Request,
        offset: int = Query(None, alias=param_offset, ge=0),
        limit: int = Query(
            None, alias=param_limit, ge=0, le=settings.BAZIS_API_PAGINATION_PAGE_SIZE_MAX or 1000
        ),
    ):
        """
        Initializes the ServicePagination instance with request data, offset, limit, and
        default settings.
        """
        self.request = request
        self.offset = offset or 0
        self.limit = settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT if limit is None else limit
        self.count = 0

    def apply(self, queryset: QuerySet):
        """
        Applies pagination to the given queryset, adjusting it based on the offset and
        limit parameters.
        """
        queryset_count = queryset.prefetch_related(None).select_related(None)
        self.count = queryset_count.count()
        if self.count == 0 or self.offset > self.count:
            return queryset.none()
        if self.limit == 0:
            return queryset.none()
        return queryset[self.offset : self.offset + self.limit]

    @cached_property
    def link_prev(self):
        """
        Generates the URL for the previous page, if applicable, based on the current
        offset and limit.
        """
        if self.limit == 0:
            return None

        if self.offset == 0:
            return None

        if (offset := self.offset - self.limit) <= 0:
            return str(self.request.url.remove_query_params(self.param_offset))

        return str(
            self.request.url.include_query_params(
                **{
                    self.param_limit: self.limit,
                    self.param_offset: offset,
                }
            )
        )

    @cached_property
    def link_next(self):
        """
        Generates the URL for the next page, if applicable, based on the current offset
        and limit.
        """
        if self.limit == 0:
            return None

        if (offset := self.offset + self.limit) >= self.count:
            return None

        return str(
            self.request.url.include_query_params(
                **{
                    self.param_limit: self.limit,
                    self.param_offset: offset,
                }
            )
        )

    @cached_property
    def link_first(self):
        """
        Generates the URL for the first page, removing the offset parameter from the
        query string.
        """
        if self.limit == 0:
            return None
        return str(self.request.url.remove_query_params(self.param_offset))

    @cached_property
    def link_last(self):
        """
        Generates the URL for the last page, calculating the appropriate offset based on
        the total count and limit.
        """
        if self.limit == 0:
            return None
        if self.count % self.limit == 0:
            offset = self.count - self.limit
        else:
            offset = self.count // self.limit * self.limit

        return str(
            self.request.url.include_query_params(
                **{
                    self.param_limit: self.limit,
                    self.param_offset: offset,
                }
            )
        )

    @cached_property
    def links(self):
        """
        Aggregates all pagination links (first, last, previous, next) into a
        PaginationLinks object.
        """
        return PaginationLinks(
            first=self.link_first,
            last=self.link_last,
            prev=self.link_prev,
            next=self.link_next,
        )

    @cached_property
    @meta_field([CrudApiAction.LIST], title=_('Pagination'))
    def pagination(self) -> PaginationMeta:
        """
        Provides pagination metadata, including count, limit, and offset, as a
        PaginationMeta object.
        """
        return PaginationMeta(
            count=self.count,
            limit=self.limit,
            offset=self.offset,
        )
