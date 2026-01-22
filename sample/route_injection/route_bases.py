from fastapi import Depends

from bazis.core.models_abstract import JsonApiMixin
from bazis.core.routes_abstract.initial import inject_make
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.enums import CrudApiAction

from route_injection.services import TimestampService


class TimestampsJsonapiRouteBase(JsonapiRouteBase):
    """Base class for routes with a custom service that adds a meta field with timestamps of the request execution."""

    abstract: bool = True

    @inject_make(CrudApiAction.LIST, CrudApiAction.RETRIEVE)
    class InjectTimestamps:
        """Add a custom service."""

        timestamp_service: TimestampService = Depends()

    def list(self):
        """Populate the custom meta field of the list via the service."""
        self.inject.timestamp_service.set_before_db_request_timestamp()
        qs = super().list()
        self.inject.timestamp_service.set_after_db_request_timestamp()
        return qs

    def retrieve(
        self, item_id: str, with_lock: bool = False, is_force: bool = False
    ) -> JsonApiMixin:
        """Populate the custom meta field of the list via the service."""
        self.inject.timestamp_service.set_before_db_request_timestamp()
        qs = super().retrieve(item_id, with_lock, is_force)
        self.inject.timestamp_service.set_after_db_request_timestamp()
        return qs

    @inject_make('warning_inject_make_tag')
    class WarningInject:
        """Warning inject."""
