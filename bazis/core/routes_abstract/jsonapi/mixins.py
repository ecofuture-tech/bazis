from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from bazis.core.schemas.enums import AccessAction, ApiAction, CrudApiAction
from bazis.core.schemas.fields import SchemaFields

from .route_base import JsonapiRouteBase


User = get_user_model()


class UniqNumberRouteMixin(JsonapiRouteBase):
    """
    A mixin for routes that handle models with unique numbers.
    It maps the 'number' filter to the 'uniq_number' field in the model.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    fields = {
        None: SchemaFields(
            include={
                'number': None,
            },
            exclude={
                'uniq_number': None,
            },
        ),
    }

    def __init__(self, *args, **kwargs):
        """
        Initializes the UniqNumberRouteMixin class, setting up the filters_aliases to
        map 'number' to 'uniq_number'.
        """
        super().__init__(*args, **kwargs)
        self.filters_aliases.update(
            {
                'number': 'uniq_number',
            }
        )


class DtRouteMixin(JsonapiRouteBase):
    """
    A mixin class for JsonapiRouteBase that excludes 'dt_created' and 'dt_updated'
    fields during CREATE and UPDATE actions.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    fields: dict[ApiAction, SchemaFields] = {
        CrudApiAction.CREATE: SchemaFields(
            exclude={'dt_created': None, 'dt_updated': None},
        ),
        CrudApiAction.UPDATE: SchemaFields(
            exclude={'dt_created': None, 'dt_updated': None},
        ),
    }


class RestrictedQsRouteMixin(JsonapiRouteBase):
    """
    A mixin class for JsonapiRouteBase that provides a method to restrict the
    queryset based on access action and user.

    Tags: RAG, EXPORT
    """

    abstract: bool = True

    @classmethod
    def restrict_queryset(
        cls, qs: QuerySet, access_action: AccessAction, user: User = None, **kwargs
    ) -> QuerySet:
        """
        Restricts the provided queryset based on the specified access action and user.
        This method can be overridden to apply custom restrictions.
        """
        return qs
