from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RelationshipData(BaseModel):
    id: str
    type: str


class RelationshipItem(BaseModel):
    data: RelationshipData


class CarrierTaskRelationships(BaseModel):
    vehicle: RelationshipItem
    driver: RelationshipItem
    org_owner: RelationshipItem


class CarrierTaskAttributes(BaseModel):
    dt_created: datetime
    dt_updated: datetime
    dt_start: datetime
    dt_finish: datetime | None
    fact_waste_weight: str | None


class CarrierTaskResponseData(BaseModel):
    id: str
    type: Literal['route_injection.carrier_task']
    bs_action: Literal['view'] = Field(..., alias='bs:action')
    attributes: CarrierTaskAttributes
    relationships: CarrierTaskRelationships

    class Config:
        populate_by_name = True


class CarrierTaskResponse(BaseModel):
    data: CarrierTaskResponseData
