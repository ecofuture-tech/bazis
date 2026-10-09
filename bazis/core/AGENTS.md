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

Files: the application redirects `MEDIA_URL` to `MEDIA_HOST_URL` (else `ADMIN_HOST_URL`)
and `STATIC_URL` to `ADMIN_HOST_URL`. Without such a host (or when the redirect would
point at the request itself: the same host, port and path, whatever the scheme), in DEBUG
it serves the files from `MEDIA_ROOT` / `STATIC_ROOT` itself, the media with `X-Content-
Type-Options: nosniff`, `Content-Security-Policy: sandbox` and, except raster images,
`Content-Disposition: attachment`; without DEBUG it answers 404 naming the setting. In
production serve them by the web server or a media host (`BS_MEDIA_HOST_URL`); do not
mount `MEDIA_ROOT` in the project. The loop is detected against the Host of the request: a
proxy in front of the application must preserve the Host header (not rewrite it to an
internal address), or a host setting that names the public address redirects to itself.

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
libraries that are not apps are not included. When two catalogs translate the same msgid,
the first one wins, in every process: the list depends only on the settings
(`bazis_doctor` warns when two Bazis packages differ, `bazis.W004`). To change a
translation of a package, translate the msgid in the project's `locale`, or give the field
its own title (`verbose_name` of the model field, or `SchemaField(title=...)` in `fields` of
the route). Write the msgids in English (`gettext_lazy`): English needs no catalog, every
other language of `LANGUAGES` does (`bazis.W005` lists the Bazis packages left untranslated).

Languages: `BS_LANGUAGES` (default `[["en", "English"]]`) and `BS_LANGUAGE_CODE` (default
`en`, one of them). The language of a request is the query parameter `lang`, otherwise the
header `Accept-Language` by weight, matched against `LANGUAGES` by code or base code
(`ru-RU` is `ru`), otherwise `LANGUAGE_CODE` (`bazis.core.i18n.request_language`). The
schemas are built once per process for all the languages: the titles, descriptions and
choice labels (`enumDict`) are translated when a JSON schema is generated, so the
`schema_*` routes answer in the language of the request and `/openapi.json` too (built
once per language; `app.openapi()` is in the active language, export it under
`translation.override(settings.LANGUAGE_CODE)`, or fetch it with `?lang=` or without
`Accept-Language`). Every HTTP response has `Vary: Accept-Language`. Keep titles lazy (`gettext_lazy`,
`verbose_name`): a `str` is fixed in the language of the code that made it. Compose the
names of models and fields with `format_lazy`, not an f-string: a name made at import is in
the language active then and gets into the migrations (the names of the models
`AbstractForeignKey` makes, such as the status history of bazis-statusy, are lazy, and
`makemigrations` writes the English msgids). In tests set
`LANGUAGES` with `monkeypatch.setattr(settings, ...)`, not with the `settings` fixture or
`override_settings`: their signal makes Django replace the per-request translations of the
core with thread-local ones.

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
- Invariants: override `validate_item(self, changes)` and raise a Django
  `ValidationError` (a dict by field) to refuse a write:

  ```python
  from django.core.exceptions import ValidationError
  from django.utils.translation import gettext_lazy as _

  class Booking(DtMixin, UuidMixin, JsonApiMixin):
      def validate_item(self, changes):
          if changes.is_new or changes.fields & {'room', 'dt_start', 'dt_end'}:
              # serializes the bookings of the room until the commit of the request
              Room.objects.select_for_update().get(pk=self.room_id)
              if Booking.objects.filter(room=self.room_id, dt_start__lt=self.dt_end,
                                        dt_end__gt=self.dt_start).exclude(pk=self.pk).exists():
                  raise ValidationError({'room': _('The room is booked at this time')})
  ```

  The core calls it once per write of the item, after the values (and the many-to-many
  relations) are in the database and before the commit, in the same transaction: the
  create, update and relationships endpoints (once at the end of the request, with the
  included items), the transits of bazis-statusy, and any other `save()` or change of a
  many-to-many relation through a manager (the admin, scripts, commands, background
  tasks; `set()` and a form's `save_m2m()` once, on the final state). `changes`
  (`bazis.core.item_validation.ItemChanges`): `fields` (the attributes and foreign keys
  whose values changed, all of them for a new item, without the `auto_now` timestamps),
  `relations` (the to-many and reverse relations set), `is_new`, `source` (`create`,
  `update`, `relationships`, `transit`, `save`) and `user` (of the route, the transit or
  the admin request; None in a script); in a block the outermost declaration wins (a
  transit in `hook_after_create` reports `create`). A failure answers 422
  `ERR_ITEM_INVALID` with the pointer `/data/attributes/<f>` or `/data/relationships/<f>`
  (`/included/<i>/...` for an included item; on the relationships endpoints the parameter
  `/related_field_name`) and rolls the write back; outside the API the save raises
  `bazis.core.errors.JsonApiItemInvalidException` (in a savepoint of its own: the
  transaction goes on). A many-to-many `add()`/`remove()`/`clear()` has no savepoint:
  when its validation fails inside a transaction, roll that transaction (or `atomic()`
  block) back. Several writes of a script are validated once at the end in
  `with defer_validate_item(user=...):` (`bazis.core.item_validation`; an item written
  again after `scope.validate()` is validated again); `ValidateItemAdminMixin`
  (`bazis.core.admin_abstract`) does it for the change form of the admin and shows the
  errors in the form. The routes link the items of a reverse foreign key of a model that
  validates one by one, with `save(update_fields=[<fk>])`. Not validated:
  `QuerySet.update()`, `bulk_create()`, `bulk_update()`, a reverse foreign key manager with
  `bulk=True` outside the routes, `Through.objects.create()`, `loaddata` and the
  deserialization (raw saves and raw many-to-many changes), raw SQL and deletion;
  `item.tags(manager='...').set()` validates its removal and its addition each. Do not
  write the item in `validate_item` (its own writes there are not validated again); items
  whose `validate_item` save each other are stopped after 10 validations of one item in one
  validation pass (`ImproperlyConfigured`). A model that does not override it pays nothing.
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
  `actions_exclude`. A route class of a proxy model has no create and update (its own
  `actions_exclude`, the inherited list is not changed). There is no route that shows an
  item past its schema (`/{item_id}/dict_data/` was removed in 2.11.0); a project that
  needs one defines it in its route class and restricts it itself.
- Reverse relations and calculated fields are not in the schemas by default: add them with
  `SchemaFields(include=...)`. Writable relations are those of the UPDATE (CREATE) schema.
  A relation read-only there (`SchemaField(read_only=True)`, the field permission
  `readonly` of bazis-permit) is ignored by an update, and the relationships endpoints
  refuse it as a relation that is not in the schema: 403 `ERR_RELATIONSHIP_READONLY` with
  `source.parameter` `/related_field_name`.
- Visibility of the objects of a model for the other routes: override the classmethod
  `restrict_queryset(qs, access_action, user=None, **kwargs)` of `RestrictedQsRouteMixin`
  (`bazis.core.routes_abstract.jsonapi`) in the default route of the model (the core
  calls it on the class with `user`, the `inject.user` of the calling route: None if the
  route has no user, or anonymous; never raise for them, return what a user without
  authentication may see, e.g. `qs.none()`, or fall back to a request-level user of the
  package; the route of the request is `JsonApiMixin.CTX_ROUTE.get()`; accept
  `**kwargs`). A relationship of a created or changed item (create, update, the
  relationships endpoints) links only the objects it returns for `view`, a reverse
  relationship only the objects it returns for `change` (their foreign key changes), both
  for the objects whose link changes; otherwise 403 `ERR_RELATION_ACCESS` with the pointer
  `/data/relationships/<field>`. `included` shows only the visible objects (the
  relationship keeps the identifiers), and the filter, sorting and search of the other
  routes reach only the visible objects through a relation. The objects of a model whose
  default route does not
  override `restrict_queryset` (or that has no route) are not checked and not queried.
  `relation_targets_check = False` turns the check off for the relationships of a route.
  The route's own list and item do not use `restrict_queryset` by themselves: apply it in
  `get_queryset` too.
- The default route of a model (`Model.get_default_route()`) is the last defined route
  class of the model (abstract ones never), unless one declares `default_route = True` in
  its class body (not inherited). With several route sets of a model that restrict its
  objects differently, declare it (`bazis_doctor` warns, `bazis.W003`).
- Logic around writes: the hooks of the route (below). They are for the side effects of
  the writes of the route; a rule about the item (an invariant) belongs in `validate_item`
  of the model (see Models), which no way of writing bypasses.
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
  routers by module name: `router.register('crm.router')` (its `router`). `register` also
  takes a router object (`router.register(files_router)`, a `BazisRouter`); the prefix of
  `as_router()` is `get_url_prefix()` of the route class.

### Fields of a route

`fields = {<action or None>: SchemaFields(...)}` (`None`: every action). By default a schema
has the attributes and the forward relations of the model. `origin={...}` replaces them
with the listed fields (a projection), `include={...}` adds fields (reverse relations,
calculated fields, a `SchemaField` that overrides one), `exclude={...}` removes fields and
wins over `include`. The entries of an action are read along the MRO of the route, the
parent classes first, and in each class its `None` entry, then its entry of the action:
`include` and `exclude` add up, the last `origin` wins (the action entry of the route,
else its `None` entry, else the entries of the parents; so a `None` entry of a child
overrides an action entry of its parent). `is_inherit=False` on the entry of an action
leaves out the `None` entry of the same class only.

### Writes of a route: hooks and their order

A request runs in one transaction: an exception anywhere rolls all its writes back.

- create (`POST /`): the item is built from the attributes and the to-one relations, not
  saved → `hook_before_create(item)` → the item is saved, then its to-many relations →
  `hook_after_create(item)` → the `included` items, each the same way → `validate_item` of
  every item written.
- update (`PATCH /{item_id}/`): `hook_before_update(item)` sees the values in the database
  (the data of the request is not applied and not passed) → the data is applied and saved
  → `hook_after_update(item)` sees the new values → the `included` items → `validate_item`.
- the relationships endpoints: `hook_before_relationships_change(item, data,
  related_field_name, action)` (`action`: `add`, `set`, `remove`) → the change →
  `hook_after_relationships_change(...)` → `validate_item`. The create and update hooks do
  not run. Delete has no hooks.
- The hooks see an item that is not validated yet: `validate_item` runs once per item at
  the end of the request, with the writes of the hooks. A hook that needs a valid item
  (before a transit of bazis-statusy, whose validators would answer first, or before a
  notification) validates the writes so far: `with defer_validate_item() as scope:
  scope.validate()` (`bazis.core.item_validation`); what is written after it is validated
  again at the end.
- The old and the new values: read the old ones in `hook_before_update`, or use
  `changes.fields` in `validate_item`.
- The packages override hooks too (bazis-author sets `author` in `hook_before_create`,
  bazis-users and bazis-permit check in theirs): an override calls `super()`.

### Errors

- A rule about an item: raise a Django `ValidationError({'<field>': message})` in
  `validate_item`: 422 `ERR_ITEM_INVALID`, pointer `/data/attributes/<field>` or
  `/data/relationships/<field>` (`/data` without a field). A Django `ValidationError`
  raised anywhere else (a hook, a route) is a 500. The routes do not call `full_clean()`:
  `Model.clean()` and the `validators` of the fields do not run on the API.
- From a hook or a custom route: `raise JsonApiBazisException([JsonApiBazisError(message,
  loc=('body', 'data', 'attributes', '<field>'), code='ERR_...')], status=422)`
  (`bazis.core.errors`). The status of the response is the status of the exception (400
  by default); each error keeps its own (422 by default). `loc` is the source of the error:
  starting with `path`, the parameter `/<rest>`; otherwise the pointer, joined with `/`,
  without a leading `body` (`('attributes', f)` is `/attributes/f`, not a pointer into
  the document).
- What the application answers: `JsonApiBazisException` with its status and errors; the
  errors of the request schemas 422 `ERR_VALIDATE` (the title is the Pydantic error type,
  the detail its English message); an `item_id` that cannot be a key 404; a
  `JsonApiHttpException` (`JsonApi403Exception` is `ERR_FORBIDDEN`) its status, `code`
  and `detail`; another `HTTPException` (an unknown path 404, a wrong method 405) its
  status and `detail`, with `ERR_REQUEST` when a route raised it; a query error 400
  `ERR_FILTER`; any
  other exception 500 (the traceback in `detail` only with DEBUG), also an
  `IntegrityError` of a constraint checked at the commit (a foreign key to a missing
  object).
- The pointers: the errors of the request schemas (`ERR_VALIDATE`), of `validate_item`
  (`ERR_ITEM_INVALID`) and of the relation access (`ERR_RELATION_ACCESS`) point into the
  request document the same way: `/data/attributes/<f>`, `/data/relationships/<f>`,
  `/data/id`, and `/included/<i>/attributes/<f>` for the included item at index `i`;
  `source.id` and `source.type` name the item of an `ERR_VALIDATE` when the document gives
  its id. A related id that cannot be a key of the related model is an `ERR_VALIDATE` of
  its identifier (`/data/relationships/<f>/data/<i>/id`); a document without `data` is
  `missing` at `/data`. On the relationships endpoints, whose body is the `data` of the
  relationship, `ERR_VALIDATE` points into that body: `/data`, `/data/<i>/id` (`/data/id`).
  Up to 2.10 `ERR_VALIDATE` pointed to `/attributes/<f>` and `/relationships/<f>`, also for
  an included item: a client that also serves older servers reads both forms.
- The titles and the fixed details of the errors of the core follow the language of the
  request (`ru` is translated); the Pydantic messages and the diagnostics of `ERR_FILTER`
  are English.

### Several route sets of a model, read-only routes

- A second route set of a model (a projection, a public calendar) needs its own URL:
  override the classmethod `get_url_prefix()` (by default the resource path of the model,
  `/<app>/<model>`), e.g. `return '/rooms/occupancy'`, and mark the main one
  `default_route = True` (`bazis.W003`). Its own list and items are its `get_queryset`;
  the relationships, `included` and filters of the other routes use the `restrict_queryset`
  of the default route.
- A read-only route lists its actions: `actions = ['action_list', 'action_retrieve',
  'action_schema_list', 'action_schema_retrieve']` (or `as_router(actions=[...])`). The
  writes are `action_create`, `action_update`, `action_destroy`, `action_post_relationships`,
  `action_update_relationships`, `action_delete_relationships` and their schemas
  `action_schema_create`, `action_schema_update`; the other actions are `action_list_id`
  (`/_id/`) and `get_route_filter_fields`. No action shows the attributes of an item past
  the schema of the route (the `dict_data` route was removed in 2.11.0). A route class of
  a proxy model excludes `action_create` and `action_update` in a list of its own.

## API conventions

- `filter` is one expression: `filter=status=new&price__gte=20`, `filter=(a=1|b=2)`,
  `~a=1` (not), nested fields `filter=customer__name=Acme` (an `EXISTS` subquery),
  `customer__exists=true|false` (`customer__isnull` is the opposite), full-text
  `$search=text` (the search fields of the route) or `customer__$search=text` (the search
  fields of the default route of the customers), `crm.customer=<id>,<id>` (the objects
  related to those customers); `search=text` searches the search fields of the route.
- The filter, `sort` and `search` reach only what the route shows the user
  (`BAZIS_FILTERS_STRICT`, on by default since 2.9): a key starts with a field of the LIST
  schema of the route (its `fields`; `filterLabel`/`orderLabel` of the schema) or `id` (`pk`); a
  relation of it leads into the objects the default route of the related model shows (its
  `restrict_queryset` for `view` with the user of the route), where the key goes on with
  the fields of the LIST schema of that route (a model without a route: only `id`/`pk`,
  `exists`, `isnull`). `sort` goes through to-one relations only (an invisible object sorts
  as null; a relation itself sorts by the key of the related object); the search uses only
  the `search_fields` of the route that are fields of its LIST schema (`bazis.W007` warns
  about the others; `route_search_fields(route_cls)` of `bazis.core.utils.query_complex`
  lists the ones searched), a route without them has no search. Anything else is
  400 `ERR_FILTER` (pointer `/query/filter`, `/query/sort` or `/query/search`), the same
  answer as for a field that does not exist: to filter, sort or search by a field, show it
  in the LIST schema of the route. `filters_aliases` of the route are not checked (the
  relations they lead to are). `QueryToOrm`/`SearchToOrm` without `scope` (permission
  conditions, `filter:` restrictions) and the services with `scope=None` are not
  restricted. A package that changes the LIST schema per user overrides the classmethod
  `query_fields(user=None, **kwargs)` of the route. `BS_BAZIS_FILTERS_STRICT=false`
  restores the unrestricted queries of 2.8 for a transition (`bazis.W006`); it will be
  removed.
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
- `sort=-dt_created,number,customer__name`, `page[limit]` / `page[offset]`
  (`BAZIS_API_PAGINATION_PAGE_SIZE_MAX` caps the limit), `include=customer,items`,
  `fields[crm.order]=number,customer` (sparse fieldsets).
- Errors are JSON:API error objects (see Errors).

## Rules

- Every way of changing an object goes through the checks of an update: do not change
  relations in custom endpoints without the route (use `relationships_change`, which
  applies the update schema, the visibility of the targets, the `filter:` restrictions
  and the hooks).
- Keep an invariant of an item (no overlap, a limit, a consistency of fields) in
  `validate_item` of the model, not in the hooks of a route: the hooks of create and
  update do not run for the relationships endpoints, the transits, the admin or `save()`.
- Restrict the objects of a model that a user must not see in `restrict_queryset` of its
  default route, not only in `get_queryset`: `get_queryset` restricts the route's own
  list and item, the relationships, `included` and the filters through a relation of the
  other routes use `restrict_queryset`.
- A route that hides fields of its model (a projection with `fields`) hides them from the
  filter, the sorting and the search too; do not list hidden fields in `search_fields`.
- Do not access `settings.<dynamic setting>` at import time: dynamic settings are read from
  the database (constance).
- Do not edit generated schemas by hand; change the model or `fields` of the route.
