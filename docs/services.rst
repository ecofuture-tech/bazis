Services
=========================

JsonapiRouteBase allows dynamically connecting individual services for different types of ApiAction operations, such as CrudApiAction.LIST and CrudApiAction.RETRIEVE.

For example, you can write a service to supplement the meta response with timestamps made before and after executing the database request and the calculated execution time between them.

.. literalinclude:: ../sample/route_injection/services.py
    :language: python
    :pyobject: TimestampService

The method that will return the meta timestamps should be wrapped with the @meta_field([ApiAction]) decorator, specifying the corresponding ApiAction (CrudApiAction.LIST and CrudApiAction.RETRIEVE), and the returned data structure must be a pydantic BaseModel.

.. literalinclude:: ../sample/route_injection/services.py
    :language: python
    :pyobject: TimestampsMeta

The custom service should be connected to a descendant of JsonapiRouteBase, for example, TimestampsJsonapiRouteBase, by adding a class wrapped with the @inject_make(ApiAction) decorator while specifying the corresponding ApiAction (CrudApiAction.LIST and CrudApiAction.RETRIEVE) and supplementing the corresponding data retrieval methods with new logic.

.. literalinclude:: ../sample/route_injection/route_bases.py
    :language: python
    :pyobject: TimestampsJsonapiRouteBase

The resulting custom TimestampsJsonapiRouteBase can be used to describe routes, for example for the Vehicle model.

.. literalinclude:: ../sample/route_injection/routes.py
    :language: python
    :pyobject: VehicleRouteBase

As a result, a request to Vehicle with the meta=timestamps parameter will be enriched with timestamp data.

.. code-block:: bash

    curl '/api/v1/route_injection/vehicle/{vehicle_id}/?meta=timestamps'

.. code-block:: python

    expected_response = {
        "data": {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "type": "route_injection.vehicle",
            "bs:action": "view",
            "attributes": {
                "gnum": "A123BC",
                "dt_created": "2025-04-27T12:28:17.280293Z",
                "dt_updated": "2025-04-27T12:28:17.280293Z",
            },
            "relationships": {
                "vehicle_model": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
                        "type": "route_injection.vehicle_model"
                    }
                }
            }
        },
        "meta": {
            "timestamps": {
                "before_db_request_timestamp": "2025-04-29T12:28:17",
                "after_db_request_timestamp": "2025-04-29T12:28:17",
                "db_request_duration_ms": 3
            }
        }
    }