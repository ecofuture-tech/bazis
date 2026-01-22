from datetime import datetime

from django.apps import apps

from fastapi import HTTPException

from pydantic import BaseModel

from bazis.core.routes_abstract.initial import http_get, http_patch
from bazis.core.routes_abstract.jsonapi import (
    JsonApiResponse,
    JsonapiRouteBase,
    api_action_jsonapi_init,
)
from bazis.core.schemas.enums import ApiAction, CrudApiAction
from bazis.core.schemas.fields import SchemaFields

from .route_bases import TimestampsJsonapiRouteBase
from .schemas import CarrierTaskResponse


class CarrierTaskRouteSet(JsonapiRouteBase):
    """Route for CarrierTaskRouteSet"""

    model = apps.get_model('route_injection.CarrierTask')


class VehicleModelRouteBase(JsonapiRouteBase):
    """Route for VehicleModelRouteBase"""

    model = apps.get_model('route_injection.VehicleModel')


class VehicleBrandRouteBase(JsonapiRouteBase):
    """Route for VehicleBrandRouteBase"""

    model = apps.get_model('route_injection.VehicleBrand')

    fields: dict[ApiAction, SchemaFields] = {
        None: SchemaFields(
            exclude={'dt_created': None},
        ),
    }


class VehicleCurrentCarrierTaskRequest(BaseModel):
    driver_id: str | None = None
    dt_finish: datetime | None = None


class VehicleRouteBase(TimestampsJsonapiRouteBase):
    """Route for Vehicle"""

    model = apps.get_model('route_injection.Vehicle')


class VehicleCarrierTaskRouteBase(JsonapiRouteBase):
    """Route for Vehicle"""

    model = apps.get_model('route_injection.Vehicle')

    @http_get('/some_statics/', inject_tags=[CrudApiAction.LIST])
    def get_some_statics(self, **kwargs) -> list[dict]:
        # Check with correct response description
        return [{'k1': 'v1'}, {'k2': 'v2'}]

    @http_get('/some_statics_negative_1/', inject_tags=[CrudApiAction.LIST])
    def get_some_statics_negative_1(self, **kwargs):
        # Reproduce error when response description is missing
        return [{'k1': 'v1'}, {'k2': 'v2'}]

    @http_get('/some_statics_negative_2/', inject_tags=[CrudApiAction.LIST])
    def get_some_statics_negative_2(self, **kwargs) -> dict:
        # Reproduce error when response description is incorrect
        return [{'k1': 'v1'}, {'k2': 'v2'}]

    @http_get(
        '/{item_id}/current_carrier_task/',
        response_model=CarrierTaskResponse,  # pydantic model
        endpoint_callbacks=[api_action_jsonapi_init],
    )
    def get_current_carrier_task(self, item_id: str, **kwargs):
        vehicle = self.set_item(item_id)

        task_queryset = vehicle.get_tasks_for_vehicle(item_id)

        if not task_queryset.exists():
            raise HTTPException(status_code=404, detail='Tasks not found')

        task = task_queryset.first()

        return {
            'data': {
                'id': str(task.id),
                'type': 'route_injection.carrier_task',
                'bs:action': 'view',
                'attributes': {
                    'dt_created': task.dt_created.isoformat(),
                    'dt_updated': task.dt_updated.isoformat(),
                    'dt_start': task.dt_start.isoformat() if task.dt_start else None,
                    'dt_finish': task.dt_finish.isoformat() if task.dt_finish else None,
                    'fact_waste_weight': (
                        str(task.fact_waste_weight) if task.fact_waste_weight else None
                    ),
                },
                'relationships': {
                    'vehicle': {
                        'data': {
                            'id': str(task.vehicle.id),
                            'type': 'route_injection.vehicle',
                        }
                    },
                    'driver': {
                        'data': {
                            'id': str(task.driver.id),
                            'type': 'route_injection.driver',
                        }
                    },
                    'org_owner': {
                        'data': {
                            'id': str(task.org_owner.id),
                            'type': 'route_injection.organization',
                        }
                    },
                },
            }
        }

    @http_patch(
        '/{item_id}/current_carrier_task/',
        response_model_route=CarrierTaskRouteSet.action_retrieve,  # wrapped in an @http_ RouteBase method whose response model is needed
    )
    def patch_current_carrier_task(
        self, item_id: str, data: VehicleCurrentCarrierTaskRequest, **kwargs
    ):
        vehicle = self.set_item(item_id)
        tasks_queryset = vehicle.get_tasks_for_vehicle(item_id)

        if not tasks_queryset.exists():
            raise HTTPException(status_code=404, detail='Tasks not found')

        task = tasks_queryset.first()

        if data.dt_finish:
            task.dt_finish = data.dt_finish
        if data.driver_id:
            task.driver_id = data.driver_id

        task.save()

        return task

    @http_get(
        '/{item_id}/first_carrier_task/',
        response_model=CarrierTaskRouteSet.endpoint_make(
            CarrierTaskRouteSet.routes_ctx['action_retrieve']
        ).route_params.response_model,
        response_model_exclude_unset=True,
        response_class=JsonApiResponse,
    )
    def get_last_carrier_task(self, item_id: str, **kwargs):
        vehicle = self.set_item(item_id)

        task_queryset = vehicle.get_tasks_for_vehicle(item_id)

        if not task_queryset.exists():
            raise HTTPException(status_code=404, detail='Tasks not found')

        task = task_queryset.last()

        return task
