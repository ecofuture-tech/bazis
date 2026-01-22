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
