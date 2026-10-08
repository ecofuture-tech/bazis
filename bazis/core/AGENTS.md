# Bazis core — guide for AI agents

Bazis builds JSON:API services on Django (models, admin, migrations) and FastAPI (routing,
OpenAPI) with Pydantic schemas generated from the models. The core is the package `bazis`
(module `bazis.core`); every other feature is a separate package `bazis-<name>` (module
`bazis.contrib.<name>`) with its own `AGENTS.md` and `bazis_manifest.toml`. Install only
the packages the project needs.

Facts about a concrete project come from the project itself, not from this text:

- `python manage.py bazis_introspect [packages|settings|models|routes]` prints the
  installed Bazis packages (with their manifests), the settings, the JSON:API models and
  the routes as JSON;
- `python manage.py bazis_doctor [--deploy] [--json]` runs the system checks of Django and
  of the Bazis packages and fails on errors. Run it after every change.

With bazis-mcp installed, the MCP server `bazis-mcp` gives the same facts and checks and the
guides of all Bazis packages, also the ones not installed.

## Project layout

```
project.env              # BS_* environment variables (settings)
manage.py
sample/settings.py       # `import bazis.core.configure` builds the Django settings
sample/router.py         # root router, BS_BAZIS_ROUTER_MODULE=sample.router
<app>/models.py          # models
<app>/routes.py          # route classes
<app>/router.py          # `router = BazisRouter(...)` of the app
<app>/conf.py            # optional `Settings(BazisSettings)` of the app
```

Settings are environment variables with the `BS_` prefix (`BS_DEBUG`, `BS_SECRET_KEY`,
`BS_DATABASES__DEFAULT__HOST`, lists and dicts as JSON). Apps, including Bazis packages,
are listed in `BS_INSTALLED_APPS` (`'["myapp", "bazis.contrib.permit"]'`). The settings
(`conf.py`) of all installed Bazis packages are loaded, also of the packages the project does
not use, and a `BS_*` variable is read only if a `conf.py` declares the setting. The core
declares the Django settings a project sets with `BS_*`, with the Django defaults, including
`AUTH_USER_MODEL` and `AUTHENTICATION_BACKENDS` (`BS_AUTH_USER_MODEL=users.User`). A package
declares only the settings it owns (`BAZIS_*`, `KAFKA_*`, or its own names such as
`AUTH_ANONYMOUS_USER_MODEL` of bazis-users), inert without its code, and never redeclares or
defaults a Django setting (bazis-users and bazis-authing drop theirs in their next releases).
`BS_BAZIS_APPS` (or `BS_BAZIS_CONFIG_APPS`) is only an explicit override: the exact list of
the packages to load the settings from. Leave it unset; `'[]'` turns off the settings of all Bazis packages, also
of the ones the project uses (`bazis_doctor` warns, `bazis.W002`). Requirements:
PostgreSQL with PostGIS and Redis (`BS_CACHES__DEFAULT__LOCATION`). `DEBUG` is true by
default: set `BS_DEBUG=false` and `BS_SECRET_KEY` (required without DEBUG) in production.

Translations: the core puts into `LOCALE_PATHS` the `locale` directory of the project
(`<BASE_DIR>/locale`), then those of the installed apps in the order of `INSTALLED_APPS`
(the apps of the project included), then those of the Bazis packages that are not installed
(a project uses the abstract models of bazis-users without installing it) by name. Other
libraries that are not apps are not included. When two catalogs translate the same msgid
(`"Name"` is translated differently by bazis-permit, bazis-statusy and bazis-uploadable),
the first one wins, in every process: the list depends only on the settings. To change a translation of a package, translate the
msgid in the project's `locale`, or give the field its own title (`verbose_name` of the
model field, or `SchemaField(title=...)` in `fields` of the route).

Files: the application redirects `MEDIA_URL` to `MEDIA_HOST_URL` (else `ADMIN_HOST_URL`)
and `STATIC_URL` to `ADMIN_HOST_URL`. Without such a host (or when the host is the
application itself), in DEBUG it serves the files from `MEDIA_ROOT` / `STATIC_ROOT`
itself, the media with `X-Content-Type-Options: nosniff`, `Content-Security-Policy:
sandbox` and, except raster images, `Content-Disposition: attachment`; without DEBUG it
answers 404 naming the setting. In production serve them by the web server or a media
host (`BS_MEDIA_HOST_URL`); do not mount `MEDIA_ROOT` in the project.

## Models

```python
from django.db import models
from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin

class Order(DtMixin, UuidMixin, JsonApiMixin):
    number = models.CharField('Number', max_length=50, unique=True)
    customer = models.ForeignKey('crm.Customer', on_delete=models.PROTECT,
                                 related_name='orders')
```

- Every model and mixin inherits from `InitialBase` (the mixins above do). `JsonApiMixin`
  makes the model a JSON:API resource; its type is `<app_label>.<class name in snake_case>`
  (`CarrierTask` in the app `crm` is `crm.carrier_task`).
- A missing `Meta` is inherited from all parents (unlike plain Django).
- Calculated fields: `@calc_property([...])` from `bazis.core.utils.orm`, declared with the
  fields they need (`FieldRelated`, `FieldJson`, ...) so that the query fetches them in one
  pass; then add them to the route with `SchemaField(source=..., required=False)`.
- A callable default of a model field (`auto_now`, `timezone.now`, `uuid.uuid4`, `dict`, a
  database lookup) is never evaluated by the schemas, neither when they are built nor when
  a request or a response is validated: the field is optional, without a `default` in the
  OpenAPI, and an omitted field gets the default of the model on save (only the attributes
  sent by the client are written). Static defaults (`True`, `'new'`) stay in the OpenAPI.
  The generated OpenAPI must not depend on the process or the time (it is hashed to detect a
  stale frontend contract): do not put random or time-based values into schemas.

## Routes

```python
from django.apps import apps
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.schemas.enums import CrudApiAction
from bazis.core.schemas.fields import SchemaField, SchemaFields

class OrderRouteSet(JsonapiRouteBase):
    model = apps.get_model('crm.Order')
    fields = {
        None: SchemaFields(include={'items': None}),          # all actions
        CrudApiAction.UPDATE: SchemaFields(exclude={'number': None}),
    }
```

- A route class gives list, retrieve, create, update, destroy and the relationships
  endpoints for its model. Restrict them with `as_router(actions=[...])` or
  `actions_exclude`.
- Reverse relations and calculated fields are not in the schemas by default: add them with
  `SchemaFields(include=...)`. Writable relations are those of the UPDATE (CREATE) schema.
- Logic around writes: override `hook_before_create`, `hook_after_create`,
  `hook_before_update`, `hook_after_update` (and `hook_before/after_relationships_change`
  for the relationships endpoints). They run inside the transaction.
- Custom routes: `@http_get('/{item_id}/card/', kind=RouteKind.ITEM)` (decorators from
  `bazis.core.routes_abstract.initial`, `RouteKind` from `bazis.core.schemas.enums`). Every
  operation of a route class has the OpenAPI extension
  `x-bazis: {resource, route_set, action, kind}` (`action` is the method name,
  `kind` is collection, create, item, update, delete, relationship, schema or other);
  client generators read it instead of parsing `operationId`. Without `kind` a route is
  `other`; an override keeps the kind of the route it overrides.
- The OpenAPI operations document the errors they fail with (`SchemaErrors`): 400 and 422
  on the CRUD operations, 404 on every route of an item (`{item_id}` in the path), 403 on
  the relationships routes. The core has no authentication, so no 401 and no `security`.
  An id in the path that cannot be a primary key of the model (`not-a-uuid`) is 404, like
  a missing item, on every route of an item (also the custom ones that take the item with
  `set_item`/`get_item`).
  A route class or package that fails its routes with a status adds it by extending the
  classmethod `route_responses(route_ctx)` (call `super()`); `responses=` of a decorator
  wins. Other facts of the operation (`security`, extensions) are added the same way by
  extending `route_openapi_extra(route_ctx)` (`x-bazis` is its base; never change the route
  context there). Document only what the route can really return.
- Register: `router = BazisRouter(tags=['CRM'])`, `router.register(OrderRouteSet.as_router())`
  in `<app>/router.py`; the root router (`BazisRouter(prefix='/api/v1')`) registers the app
  routers by module name: `router.register('crm.router')`.

## API conventions

- `filter` is one expression: `filter=status=new&price__gte=20`, `filter=(a=1|b=2)`,
  `~a=1` (not), nested fields `filter=customer__name=Acme` (an `EXISTS` subquery),
  `customer__exists=true|false` (`customer__isnull` is the opposite), full-text
  `$search=text` (all text and integer fields of the model) or `customer__$search=text`;
  `search=text` searches the search fields of the route.
  The lookup suffixes after a field are not Django lookups; only these exist (plus `isnull`
  for every field):
  - text `TextField`: none (substring), `iexact`, `istartswith`, `iregex`, `search`, `$search`;
  - other scalar fields (calculated filters without `filter_field` too): none (equality),
    `gt`, `gte`, `lt`, `lte`, `iexact`, `istartswith`, `iregex`, `$search`, and `search`
    for string fields (`CharField`) only;
  - boolean: none; array: none (= `overlap`), `overlap`, `contains`, `contained_by` with
    `a,b`; range: `contains`, `contained_by`, `overlap`, `fully_lt`, `fully_gt`, `not_lt`,
    `not_gt`, `adjacent_to` with `start,end`; point: none (within 10 m), `near`, `in_bbox`.

  Any other suffix (`__in`, `__icontains`, `__contains` on a text or number field), an
  unknown field (also after a relation, such as `customer__in`) and a calculated field that
  is not `as_filter` are an error 400 `ERR_FILTER`. `iexact`/`istartswith`/`iregex`/
  `search`/`$search` apply to every word of the value. URL-encode the value of `filter`;
  the server decodes the expression once more and every value once more, so a value with
  `&|()[]~=+%` is percent-encoded twice inside the expression; quotes are removed from
  values.
- `sort=-dt_created,number`, `page[limit]` / `page[offset]`
  (`BAZIS_API_PAGINATION_PAGE_SIZE_MAX` caps the limit), `include=customer,items`,
  `fields[crm.order]=number,customer` (sparse fieldsets).
- Errors are JSON:API error objects; validation errors are 422.

## Rules

- Every way of changing an object goes through the checks of an update: do not change
  relations in custom endpoints without the route (use `relationships_change`, which
  applies the update schema, the `filter:` restrictions and the hooks).
- Do not access `settings.<dynamic setting>` at import time: dynamic settings are read from
  the database (constance).
- Do not edit generated schemas by hand; change the model or `fields` of the route.
