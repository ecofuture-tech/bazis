Endpoint callbacks
===================

The signature of `@http_...` decorators wrapping endpoint methods of route classes (inheritors of `InitialRouteBase`)
supports the ``endpoint_callbacks`` parameter — a list of callback functions called during route initialization.

.. code-block:: python

        @http_get('/', endpoint_callbacks=[api_action_jsonapi_init])

The mechanism works as follows:

1. When the application starts, the ``@http_...`` decorator passes `endpoint_callbacks` to the `http_action_decor` function.
2. The `http_action_decor` function creates a `RouteContext` instance, including the passed callbacks.
3. The resulting `RouteContext` object is saved in place of the wrapped method.

.. code-block:: python

    def http_get(..., endpoint_callbacks: list[Callable[..., None]] | None = None, ...):
        return http_action_decor(HttpMethod.GET, ..., endpoint_callbacks, ...)

.. code-block:: python

    def http_action_decor(..., endpoint_callbacks: list[Callable[..., Any] | partial] | None = None, ...):
        def decorator(func):
            ...
            return RouteContext(..., endpoint_callbacks=endpoint_callbacks, ...)
        return decorator

At the moment of route assembly (for example, in the ``router.py`` module), the ``as_router()`` method is called, which registers all
routes:

.. code-block:: python

    router.register(routes.VehicleRouteBase.as_router())

The ``as_router`` method iterates through all `RouteContext` instances and calls the ``endpoint_make`` method, which in turn executes
the callback functions:

.. code-block:: python

    @classmethod
    def as_router(cls, actions: list | None = None, actions_exclude: list | None = None):
        ...
        for route_ctx in cls.routes_ctx.values():
            ...
            cls.endpoint_make(route_ctx)

    @classmethod
    def endpoint_make(cls, route_ctx: RouteContext) -> RouteContext:
        ...
        if route_ctx.endpoint_callbacks:
            for endpoint_callback in route_ctx.endpoint_callbacks:
                endpoint_callback(cls=cls, route_ctx=route_ctx)

As can be seen from the ``endpoint_make`` signature, callback functions must support the following parameters in their signature:

- ``cls`` — reference to the route class (`RouteBase`)
- ``route_ctx`` — `RouteContext` instance

Additional parameters can be passed through ``functools.partial`` at the stage of passing arguments to the ``endpoint_callbacks`` parameter of ``@http_...`` decorators.

Example:

.. code-block:: python

    @http_get(
        '/',
        endpoint_callbacks=[
            api_action_jsonapi_init,
            partial(meta_fields_addition, api_action=CrudApiAction.LIST),
        ]
    )

**Predefined callbacks in the ``bazis`` package**

The ``bazis`` package already includes 6 predefined ``endpoint_callbacks`` used for route configuration:

1. **`api_action_jsonapi_init`**
   - Removes `None` fields from the response body (according to JSON:API specification).
   - Replaces `JSONResponse` with `JsonApiResponse`, which has ``media_type = 'application/vnd.api+json'``.
   - Adds descriptions for 400 and 422 errors to OpenAPI (via `SchemaErrors`).

   .. code-block:: python

      def api_action_jsonapi_init(cls, route_ctx: 'RouteContext'):
          route_ctx.route_params.response_model_exclude_unset = True
          route_ctx.route_params.response_class = JsonApiResponse
          route_ctx.route_params.responses = {
              HTTP_400_BAD_REQUEST: {'model': SchemaErrors},
              HTTP_422_UNPROCESSABLE_ENTITY: {'model': SchemaErrors},
          }

2. **`partial(meta_fields_addition, api_action=...)`**
   - Adds `meta` fields.
   - Most often used for pagination, but can be applied to other schemas as well.

   .. code-block:: python

      def meta_fields_addition(cls: 'JsonapiRouteBase', route_ctx: 'RouteContext', api_action: ApiAction):
          for ctx_cls in cls.get_context_classes(route_ctx).values():
              for name, meta_schema in get_meta_schemas(ctx_cls).items():
                  if api_action in meta_schema.api_actions:
                      if api_action not in cls.meta_fields:
                          cls.meta_fields[api_action] = SchemaMetaFields()
                      cls.meta_fields[api_action].include[name] = meta_schema.field_schema

3. **`partial(api_action_init, api_action=...)`**
   - Generates default schemas via factories.

   .. code-block:: python

      def api_action_init(cls, route_ctx: 'RouteContext', api_action: ApiAction):
          build_schema_defaults(cls, api_action)
          route_ctx.store['api_action'] = api_action

4. **`partial(api_action_response_init, api_action=...)`**
   - Sets the `response_model`.

   .. code-block:: python

      def api_action_response_init(cls, route_ctx: 'RouteContext', api_action: ApiAction):
            build_schema_defaults(cls, api_action)
            route_ctx.route_params.response_model = cls.schema_defaults[api_action]
            route_ctx.store['api_action_response'] = api_action

5. **`partial(item_data_typing, api_action=...)`**
   - Used during creation and update when a request body is required.
   - Replaces the annotation of the `item_data` parameter in the route signature with the corresponding Pydantic schema.
   - Ensures correct validation and display in OpenAPI documentation.

   The signature of endpoint methods for creating and updating data provides for filling the `item_data` parameter.

   .. code-block:: python

      @http_post(
          '/',
          status_code=201,
          inject_tags=[CrudApiAction.CREATE],
      )
      def action_create(
              self,
              request: Request,
              item_data: SchemaCreateT = Body(..., media_type='application/vnd.api+json'),
              **kwargs,
      ):
          item = self.create(request._json, item_data)
          result = {
              'data': self.retrieve(str(item.id).strip(), is_force=True),
              'meta': self.get_meta_fields(CrudApiAction.RETRIEVE),
              'included': chain(*self.item.fields_for_included.values()),
          }
          return result

      @http_patch(
          '/{item_id}/',
          inject_tags=[CrudApiAction.UPDATE],
      )
      def action_update(
              self,
              item_id: str,
              request: Request,
              item_data: SchemaUpdateT = Body(..., media_type='application/vnd.api+json'),
              **kwargs,
      ):
          item = self.update(str(item_id).strip(), request._json, item_data)
          return {
              'data': self.retrieve(str(item.id).strip(), is_force=True),
              'meta': self.get_meta_fields(CrudApiAction.RETRIEVE),
              'included': chain(*self.item.fields_for_included.values()),
          }

   Placeholders `SchemaCreateT` and `SchemaUpdateT` are used for the `item_data` annotation.

   .. code-block:: python

      SchemaCreateT = TypeVar('SchemaCreateT')
      SchemaUpdateT = TypeVar('SchemaUpdateT')

   The `item_data_typing` callback is responsible for replacing these placeholders with a specific data model:

   .. code-block:: python

      def item_data_typing(cls, route_ctx: 'RouteContext', api_action: ApiAction):
          func_sig_param_replace(
              route_ctx.endpoint,
              'item_data',
              annotation=cls.schema_defaults[api_action]
          )

6. **`item_id_typing`**
   - Used when retrieving an item, updating, and deleting, when `item_id` is passed in the signature.
   - Replaces the annotation of the `item_id` parameter with the corresponding type of the `id` field, obtained from the `RETRIEVE` schema.
   - This can be `str`, `int`, `UUID`, etc., depending on the model.
   - Ensures correct validation and display of the `item_id` parameter in OpenAPI documentation.

   .. code-block:: python

      def item_id_typing(cls, route_ctx: 'RouteContext'):
          func_sig_param_replace(
              route_ctx.endpoint,
              'item_id',
              annotation=cls.schema_factories[CrudApiAction.RETRIEVE].pk_field.py_type,
          )

---

When passing the inject_tags argument with any CrudApiAction element to the @http_ decorator, base callbacks are automatically added to the created RouteContext instance through the http_action_decor function calling the crud_jsonapi_callbacks function.

.. code-block:: python

    class CrudApiAction(ApiAction):
        LIST = 'list'
        RETRIEVE = 'retrieve'
        CREATE = 'create'
        UPDATE = 'update'
        DESTROY = 'destroy'

.. code-block:: python

    def crud_jsonapi_callbacks(api_action: CrudApiAction) -> list[Callable]:
        # Setting media_type = 'application/vnd.api+json' and describing 400/422 errors — mandatory
        callbacks = [api_action_jsonapi_init]

        # Adding schemas and meta — for all actions except deletion
        if api_action != CrudApiAction.DESTROY:
            callbacks.extend([
                partial(meta_fields_addition, api_action=api_action),
                partial(api_action_schemas_init, api_action=api_action),
            ])

        # Annotation of item_data — only for CREATE and UPDATE
        if api_action in {CrudApiAction.CREATE, CrudApiAction.UPDATE}:
            callbacks.append(partial(item_data_typing, api_action=api_action))

        # Annotation of item_id — only for RETRIEVE, UPDATE and DESTROY
        if api_action in {CrudApiAction.RETRIEVE, CrudApiAction.UPDATE, CrudApiAction.DESTROY}:
            callbacks.append(item_id_typing)

        return callbacks

---

The ``endpoint_callbacks`` parameter provides a **convenient and extensible mechanism** for configuring routes through external code, **without interfering with the handler method body itself**.