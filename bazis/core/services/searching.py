from django.db.models import QuerySet

from fastapi import Depends

from typing_extensions import deprecated

from bazis.core.routes_abstract.initial import InitialRouteBase, RouteContext
from bazis.core.services.route_ctx import get_route_ctx
from bazis.core.utils.query_complex import DJANGO_SEARCH_FIELDS, SearchToOrm


class ServiceSearching:
    """
    ServiceSearching handles the search functionality for a given queryset, using
    the search fields defined in the route class.

    Tags: RAG, EXPORT
    """

    search: str
    field_related: str = None
    route_cls: type[InitialRouteBase]

    def __init__(self, search: str = None, route_ctx: RouteContext = Depends(get_route_ctx)):
        """
        Initializes the ServiceSearching class with an optional search string and a
        route context. The route context provides the route class which contains the
        search fields.
        """
        self.search = search
        self.route_cls = route_ctx.route_cls

    def apply(self, queryset: QuerySet):
        """
        Applies the search query to the provided queryset by constructing a Q object and
        filtering the queryset based on the search terms.
        """
        search = SearchToOrm(
            queryset.model, self.search, search_fields=self.route_cls.search_fields
        )
        return queryset.filter(search.q)


@deprecated('Filtering is deprecated, use bazis.core.utils.query_complex.SearchToOrm instead.')
class Searching:
    """
    Tags: RAG, EXPORT
    """

    def __init__(self, model, search, search_fields=None):
        self.model = model
        self.search = search and search.strip()
        self.search_fields = search_fields or [
            f.name for f in model._meta.get_fields() if type(f) in DJANGO_SEARCH_FIELDS
        ]

    def __call__(self):
        search = SearchToOrm(self.model, self.search, search_fields=self.search_fields)
        return search.q
