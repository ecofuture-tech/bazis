from datetime import datetime

from django.utils.translation import gettext_lazy as _

from fastapi import Request

from pydantic import BaseModel

from bazis.core.schemas.enums import CrudApiAction
from bazis.core.schemas.meta import meta_field


class TimestampsMeta(BaseModel):
    """Timestamps metadata."""

    before_db_request_timestamp: datetime
    after_db_request_timestamp: datetime
    db_request_duration_ms: int


class TimestampService:
    """Service for obtaining timestamps before and after executing a database query."""

    def __init__(self, request: Request):
        self.request = request
        self.before_db_request_timestamp: datetime | None = None
        self.after_db_request_timestamp: datetime | None = None
        self.db_request_duration_ms: int | None = None

    def set_before_db_request_timestamp(self):
        """Set the timestamp before executing a database query."""
        self.before_db_request_timestamp = datetime.now()

    def set_after_db_request_timestamp(self):
        """Set the timestamp after a database query."""
        self.after_db_request_timestamp = datetime.now()
        self.db_request_duration_ms = int(
            (self.after_db_request_timestamp - self.before_db_request_timestamp).total_seconds()
            * 1000
        )

    @meta_field([CrudApiAction.LIST, CrudApiAction.RETRIEVE], title=_('Timestamp'))
    def timestamps(self) -> TimestampsMeta:
        """Meta field with timestamps."""
        return TimestampsMeta(
            before_db_request_timestamp=self.truncate_to_seconds(self.before_db_request_timestamp),
            after_db_request_timestamp=self.truncate_to_seconds(self.after_db_request_timestamp),
            db_request_duration_ms=self.db_request_duration_ms,
        )

    def truncate_to_seconds(self, value: datetime | None) -> datetime | None:
        """Truncate a timestamp to seconds."""
        return value.replace(microsecond=0) if value else None
