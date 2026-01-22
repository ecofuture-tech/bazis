from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase


class ContextTestRouteMixin:
    @classmethod
    def get_fiter_context(cls, route: JsonapiRouteBase = None, **kwargs):
        """
        Returns a context dictionary for filtering, including the current route
        instance.
        """
        return {'_organization': '3fa85f64-5717-4562-b3fc-2c963f66afa6'}
