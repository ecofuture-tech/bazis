Response models
===============

When adding a new endpoint to a `RouteSet`, the structure of returned data (`response_model`) can be defined in one of the following ways:

1. **Using the `api_action_response_init` callback** — a callback that populates `response_model` based on the model specified in the `model` attribute of the current `RouteSet` and computed fields.
2. **Via the `response_model` parameter** in the `@http_...` decorator — explicit specification of a Pydantic-based schema.
3. **Via the `response_model_route` parameter** in the `@http_...` decorator — reference to an endpoint method of another `RouteSet` whose `response_model` needs to be reused.

The signature of `@http_` decorators provides an `endpoint_callbacks` parameter to which the api_action_response_init callback can be explicitly passed.

.. code-block:: python

    def http_get(path: str, inject_tags: list[ApiAction] | None = None, response_model: ResponseModelType = None,
                 response_model_route: RouteContext | Callable[..., Any] | None = None,
                 endpoint_callbacks: list[Callable[..., None]] | None = None, **kwargs):
        return http_action_decor(HttpMethod.GET, path, inject_tags, response_model, response_model_route,
                                 endpoint_callbacks, **kwargs)

.. code-block:: python

    @http_get(
        '/',
        endpoint_callbacks=[
            partial(api_action_response_init, api_action=CrudApiAction.LIST)
        ]
    )


The `api_action_response_init` callback first builds a schema based on model data and computed fields, then assigns it to the `response_model` attribute.

.. code-block:: python

    def api_action_response_init(cls, route_ctx: 'RouteContext', api_action: ApiAction):
        build_schema_defaults(cls, api_action)
        route_ctx.route_params.response_model = cls.schema_defaults[api_action]
        route_ctx.store['api_action_response'] = api_action

When passing the inject_tags argument with any CrudApiAction element to the @http_ decorator, base callbacks (including `api_action_response_init`) are automatically added to the created RouteContext instance through the http_action_decor function calling the crud_jsonapi_callbacks function.

.. code-block:: python

    @http_get(
        '/',
        inject_tags=[CrudApiAction.LIST],
    )

.. code-block:: python

    def http_action_decor(
        ...,
        inject_tags: list[ApiAction] | None,
        ...
    ) -> Callable[[Callable[..., Any]], RouteContext]:
        ...
        def decorator(func):
            ...
            if (
                endpoint_callbacks is None
                and inject_tags is not None
                and len(inject_tags) == 1
                and type(inject_tags[0]) is CrudApiAction
            ):
                endpoint_callbacks = list(crud_jsonapi_callbacks(inject_tags[0]))

Let's examine setting `response_model` via the `response_model` and `response_model_route` parameters using an example.

Suppose we need to add two endpoints for the `Vehicle` model: for retrieving the current carriage and for adjusting the current carriage (`CarrierTask` model).

We'll configure the retrieval endpoint with explicit `response_model=CarrierTaskResponse`, and the adjustment endpoint — with reuse of the `response_model` from the `CarrierTaskRouteSet.action_retrieve` method.

.. literalinclude:: ../sample/route_injection/schemas.py
    :language: python
    :lines: 5-41

.. literalinclude:: ../sample/route_injection/routes.py
    :language: python
    :pyobject: VehicleCarrierTaskRouteBase

Testing the current carriage retrieval endpoint:

.. code-block:: bash

    curl '/api/v1/custom_response_model/route_injection/vehicle/3fa85f64-5717-4562-b3fc-2c963f66afa7/current_carrier_task/'

Expected response:

.. code-block:: json

    {
        "data": {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "type": "route_injection.carrier_task",
            "bs:action": "view",
            "attributes": {
                "dt_created": "2025-04-29T21:31:20.280293Z",
                "dt_updated": "2025-04-29T21:32:20.280293Z",
                "dt_start": "2025-04-29T21:32:20.280293Z",
                "dt_finish": null,
                "fact_waste_weight": "4.500"
            },
            "relationships": {
                "vehicle": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
                        "type": "route_injection.vehicle"
                    }
                },
                "driver": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa8",
                        "type": "route_injection.driver"
                    }
                },
                "org_owner": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa9",
                        "type": "route_injection.organization"
                    }
                }
            }
        }
    }

Testing the current carriage update endpoint — for example, replacing the driver:

.. code-block:: bash

    curl -X 'PATCH' \
      'http://localhost:9000/api/v1/custom_response_model/route_injection/vehicle/1a9fd09a-20b0-4451-a36d-834f7d2cc1f8/current_carrier_task/' \
      -H 'accept: application/vnd.api+json' \
      -H 'Content-Type: application/json' \
      -d '{"driver_id": "3fa85f64-5717-4562-b3fc-2c963f66afa9"}'

Expected response:

.. code-block:: json

    {
        "data": {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "type": "route_injection.carrier_task",
            "bs:action": "view",
            "attributes": {
                "dt_created": "2025-04-29T21:31:20.280293Z",
                "dt_updated": "2025-04-29T21:32:20.280293Z",
                "dt_start": "2025-04-29T21:32:20.280293Z",
                "dt_finish": null,
                "fact_waste_weight": "4.500"
            },
            "relationships": {
                "vehicle": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
                        "type": "route_injection.vehicle"
                    }
                },
                "driver": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa9",
                        "type": "route_injection.driver"
                    }
                },
                "org_owner": {
                    "data": {
                        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa9",
                        "type": "route_injection.organization"
                    }
                }
            }
        }
    }