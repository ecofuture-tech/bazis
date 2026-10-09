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
- `python manage.py bazis_doctor [--deploy] [--database ALIAS] [--json]` runs the system
  checks of Django and of the Bazis packages and fails on errors. Run it after every change.
  It also runs the database checks, which compare the project with its database (such as
  the declared roles and workflows against the rows), against `default` when it can be
  reached; otherwise they are skipped with the info `bazis.database`, so a warning-free
  doctor without the database says nothing about the data (`SILENCED_SYSTEM_CHECKS`
  silences the info). `--database` (repeatable) names the databases, and one that cannot
  be reached is an error. PostgreSQL is probed with a connect timeout of 5 seconds.

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

The catalogs of the project (`<BASE_DIR>/locale` and the `locale` directories of its apps,
never those of the installed packages) are made, filled and compiled by
`python manage.py bazis_messages` (GNU gettext required); do not write a script that edits
`.po` files:

- `make`: makemessages from BASE_DIR for the languages of `LANGUAGES` but English
  (`-l ru` to choose), ignoring `.venv`, `venv`, `.scratch`, `node_modules`, `frontend`,
  `static`, `media`, `build`, `dist`, the hidden directories, `MEDIA_ROOT` and
  `STATIC_ROOT` (`-i <glob>` adds one), without the obsolete (`#~`) entries; then prints the
  status;
- `status`: JSON by language: `catalogs`, `total`, `translated`, `untranslated` and `fuzzy`
  (each entry `{"msgid", "msgctxt"?, "msgid_plural"?}`, a fuzzy one with the `msgstr`
  gettext guessed after its source changed);
- `apply <file.json>`: sets the translations of the file, drops their fuzzy flags, fills
  the header of a new catalog (not fuzzy, `Language`) and compiles the catalogs
  (`msgfmt --check-format`); prints `applied`, `unknown` (msgids not in the catalogs) and
  what stays `untranslated`/`fuzzy`. Applying the file again changes nothing, and the next
  `make` keeps the catalog as written. The file maps a language to its translations:
  `{"ru": {"Open": "Открыть", "%(n)s item": ["%(n)s предмет", "%(n)s предмета",
  "%(n)s предметов"]}}` (a plural takes the list of its forms), or to a list of entries,
  which also give the context: `{"ru": [{"msgctxt": "verb", "msgid": "Open", "msgstr":
  "Открыть"}]}`;
- `compile`: compiles the catalogs only;
- `--check` (with `status` or `apply`) fails while an entry stays untranslated or fuzzy, or
  a msgid of the file is unknown: the check of a CI.

The loop after a change of the texts: `make` → write the translations of `untranslated`
and `fuzzy` to a file → `apply` (keep the file in the project to reapply it after the next
`make`).

Languages: `BS_LANGUAGES` (default `[["en", "English"]]`) and `BS_LANGUAGE_CODE` (default
`en`, one of them). The language of a request is the query parameter `lang`, otherwise the
header `Accept-Language` by weight, matched against `LANGUAGES` by code or base code
(`ru-RU` is `ru`), otherwise `LANGUAGE_CODE` (`bazis.core.i18n.request_language`). The
schemas are built once per process for all the languages: the titles, descriptions and
choice labels (`enumDict`) are translated when a JSON schema is generated, so the
`schema_*` routes answer in the language of the request and `/openapi.json` too (built
once per language; `app.openapi()` is in the active language, export it under
`translation.override(settings.LANGUAGE_CODE)`, or fetch it with `?lang=` or without
`Accept-Language`). The lazy texts of the request and response models of custom routes
(`Field(title=_('…'), description=_('…'))`, `json_schema_extra`), of their parameters
(`Query(description=_('…'))`) and operations (`summary`) are translated in the OpenAPI
as well (bazis 2.14; before, a lazy title broke `/openapi.json`). Lazy examples go in
`json_schema_extra={'examples': [_('…')]}`: pydantic serializes `Field(examples=...)` when
it defines the model, and refuses a lazy text there. A model whose JSON schema the code
reads itself (`model_json_schema()`, outside the OpenAPI) inherits `TranslatedSchemaModel`
(`bazis.core.utils.schemas`), or passes `schema_generator=TranslatedJsonSchema`: the schema
is then in the active language too. Every HTTP response has `Vary: Accept-Language`. Keep titles lazy (`gettext_lazy`,
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
- Calculated fields: `@calc_property([...], as_filter=False)` from `bazis.core.utils.orm`
  declares what the query of the routes fetches for the property in the same pass; the
  values come to the item as attributes named by `alias` (else `source`):

  ```python
  from django.db.models import BooleanField, Case, Q, Value, When
  from django.db.models.functions import Now
  from django.utils import timezone
  from bazis.core.utils.orm import FieldAnnotate, FieldDynamic, calc_property

  class Ticket(DtMixin, UuidMixin, JsonApiMixin):
      @calc_property([FieldAnnotate(source='is_late', query=Case(
          When(Q(due__lt=Now(), done=False), then=Value(True)),
          default=Value(False), output_field=BooleanField()))], as_filter=True)
      def is_late(self) -> bool:  # the annotation replaces it; this is for other reads
          return not self.done and self.due < timezone.now()

  class Agent(DtMixin, UuidMixin, JsonApiMixin):
      @calc_property([FieldDynamic(source='tickets', func='Count', alias='open_tickets',
                                   query=Q(done=False))])
      def open_tickets(self) -> int:
          return self.open_tickets
  ```

  `FieldAnnotate(source, query)`: an expression of the row. `FieldDynamic(source=<relation>,
  ...)`: with `func` (`'Count'`, `'Sum'`, ...; `source` may end with the field,
  `tickets__hours`) a subquery aggregate over the related objects filtered by `query` (the
  `Meta.ordering` of the related model is dropped there); with `fields=[...]` a list of
  dicts of the related objects (`order_by`, `slice`); without them the related objects
  themselves (`nested=[...]` for theirs); an `alias` starting with `has_` is an `EXISTS`.
  A subquery over another model is declared by a callable that returns the field: it is
  called on the first query, so its expression may use a model declared later in the
  module or a queryset, which cannot be built while the models load:

  ```python
  from django.db.models import OuterRef, Subquery, Sum

  class Department(DtMixin, UuidMixin, JsonApiMixin):
      @calc_property([lambda: FieldAnnotate(source='spent', query=Subquery(
          Request.objects.filter(department=OuterRef('pk'), status_id='approved')
          .order_by().values('department').annotate(total=Sum('amount')).values('total')))])
      def spent(self) -> Decimal | None:
          return self.spent
  ```

  The expressions see the filter context of the route
  (`get_fiter_context(route=...)`, a classmethod to extend with `super()`): its keys that
  start with `_` are aliases of the queryset, so a subquery refers to them with
  `OuterRef('<key>')` (an expression of the row with `F('<key>')`). bazis-users puts
  `_user`, the id of the user of the request:

  ```python
  @calc_property([lambda: FieldAnnotate(source='my_open', query=Subquery(
      Ticket.objects.filter(agent=OuterRef('pk'), assignee=OuterRef('_user'), done=False)
      .order_by().values('agent').annotate(n=Count('pk')).values('n')))])
  def my_open(self) -> int | None:
      return self.my_open
  ```

  The value depends on the user of the request: it is right for the API, not for a cache
  shared between users.
  A method that takes a `DependsCalc` argument reads them from `dc.data.<alias>`. The return
  annotation is the type of the attribute. Add it to the schema of the route with
  `fields = {None: SchemaFields(include={'open_tickets': None})}` (read-only, not required;
  `SchemaField(source=..., title=...)` to rename or title it). `as_filter=True` makes it a
  key of `filter` (when it is in the LIST schema; a boolean takes `true`/`false`,
  `filter_field=` a model field class for the lookups of another type); a calculated field
  does not sort and is not a search field. For a report, put the calculated fields on a
  proxy model with a route of its own (see Several route sets).
- Numbers: `UniqNumberMixin` (`bazis.core.models_abstract`) gives the item `uniq_number`, the
  next value of a database sequence (django-sequences, installed by the core) on its first
  save, and the property `number` (its string; override it to format, calling `super()`).
  The sequence is named by `NUMBER_LABEL` (default: the resource label of the model; give
  several models one label to share the numbering). Show it with
  `include={'number': None}`, and exclude `uniq_number` from the create and update schemas
  (it is an ordinary integer field there).
- Data named in every language of the project (statuses, priorities, categories): a
  `TranslatedFieldWithFallback` of django-translated-fields (a dependency of the core, used
  by bazis-permit and bazis-statusy), a column per language:

  ```python
  from translated_fields import TranslatedFieldWithFallback

  class Priority(DtMixin, UuidMixin, JsonApiMixin):
      name = TranslatedFieldWithFallback(
          models.CharField(_('Name'), max_length=100), languages=['en', 'ru'])
  ```

  The columns are `name_en`, `name_ru` (the first language is required, the others may be
  blank; list the languages of `BS_LANGUAGES` explicitly so that the migrations do not
  depend on the settings, and add a migration with a language). The API has one attribute
  `name`, read-only, in the language of the request (the first language when its column
  is blank); `filter`, `sort` and `search` (`search_fields = ['name']`) by it use the
  column of the language of the request (a blank translation is matched and sorted as
  empty, not by the fallback: fill every language). The columns are edited in the admin
  (`translated_fields.TranslatedFieldAdmin`), or through the API when the route adds them
  (`include={'name_en': None, 'name_ru': None}`).
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
- A create or an update names only the attributes and relationships of the schema of its
  action: any other (excluded by `fields`, hidden by a field permission of bazis-permit,
  unknown) is 422 `ERR_VALIDATE` with the title `extra_forbidden` and the pointer
  `/data/attributes/<f>` (`/data/relationships/<f>`, `/included/<i>/...`); a field of the
  schema that is read-only there (calculated fields, `SchemaField(read_only=True)`, the
  permission `readonly`) is ignored. A text field (`CharField`, `TextField`) without
  `blank=True` refuses an empty value or one of only whitespace (422 `ERR_VALIDATE` at the
  field), as the forms of Django; the value is stored as sent. A field the client may
  leave empty is `blank=True`. The responses are not checked for blank values.
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
  for the objects whose link changes; otherwise 403 `ERR_RELATION_ACCESS` (pointers: see
  Errors). `included` shows only the visible objects (the
  relationship keeps the identifiers), and the filter, sorting and search of the other
  routes reach only the visible objects through a relation. The objects of a model whose
  default route does not
  override `restrict_queryset` (or that has no route) are not checked and not queried.
  `relation_targets_check = False` turns the check off for the relationships of a route.
  The route's own list and item do not use `restrict_queryset` by themselves: apply it in
  `get_queryset` too. Who calls it: the core (`route_restrict_queryset(model)` of
  `bazis.core.routes_abstract.jsonapi.mixins`) for the relationship targets of the writes,
  `included` and the filter, sort and search through a relation; bazis-permit implements it from the permissions and
  restricts the items of its routes with it; the core never applies it to the list of a
  route by itself.
- The default route of a model (`Model.get_default_route()`) is the last defined route
  class of the model (abstract ones never), unless one declares `default_route = True` in
  its class body (not inherited). With several route sets of a model that restrict its
  objects differently, declare it (`bazis_doctor` warns, `bazis.W003`).
- Logic around writes: the hooks of the route (below). They are for the side effects of
  the writes of the route; a rule about the item (an invariant) belongs in `validate_item`
  of the model (see Models), which no way of writing bypasses.
- Custom routes: `@http_get('/{item_id}/card/', kind=RouteKind.ITEM)` (decorators
  `http_get`, `http_post`, `http_put`, `http_patch`, `http_delete` from
  `bazis.core.routes_abstract.initial`, `RouteKind` from `bazis.core.schemas.enums`). The
  decorator takes the path, then `inject_tags` (the injections of an action, e.g.
  `[CrudApiAction.LIST]` for `self.inject.filtering`), `response_model` (a Pydantic model
  of the response), `kind`, and the arguments of FastAPI (`status_code`, `responses`,
  `summary`, ...). The method is the endpoint: its parameters other than `self` and
  `**kwargs` are the parameters of FastAPI (a path parameter `item_id: str`, a Pydantic
  model the JSON body, a typed name a query parameter); `self.inject.user` is the user
  with bazis-users; `self.set_item(item_id)` loads the item the route shows (404
  otherwise) and `self.item` is it then:

  ```python
  class ExportRequest(BaseModel):
      date_from: date
      date_to: date

  class ExportResponse(BaseModel):
      task: str

  class WorkOrderRouteSet(JsonapiRouteBase):
      @http_post('/export/', response_model=ExportResponse, kind=RouteKind.OTHER)
      def action_export(self, data: ExportRequest, **kwargs):
          ...
          return ExportResponse(task=str(task.pk))

      @http_post('/{item_id}/close/', kind=RouteKind.OTHER)
      def action_close(self, item_id: str, **kwargs):
          item = self.set_item(item_id)
          ...
  ```

  A route that changes the item goes through the checks of an update (see Rules). Every
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
- The pointers (`source`) of the errors of the core, by code. Create and update point into
  the request document; an included item is `/included/<i>` instead of `/data`, `<i>` its
  index in the `included` of the document. The relationships endpoints point into their
  body, the `data` of the relationship.
  - `ERR_VALIDATE`: `/data/attributes/<f>`, `/data/relationships/<f>/...`, `/data/id`, `/data`
    (`missing` for a document without `data`); a related id that cannot be a key of the
    related model at its identifier, `/data/relationships/<f>/data/<j>/id`; `source.id` and
    `source.type` name the item when the document gives its id. On the relationships
    endpoints `/data`, `/data/<j>/id` (`/data/id`).
  - `ERR_ITEM_INVALID`: `/data/attributes/<f>`, `/data/relationships/<f>`, `/data`. On the
    relationships endpoints the parameter `/related_field_name`.
  - `ERR_INCLUDE` (400): `/query/include`. `ERR_FILTER` (400): `/query/filter`,
    `/query/sort`, `/query/search`.
  - `ERR_RELATION_ACCESS`: `/data/relationships/<f>`. On the relationships endpoints
    `/data/<j>`, the refused identifier of a to-many relationship, else `/data` (a to-one
    relationship, or an object the change unlinks).
  Up to 2.10 `ERR_VALIDATE` pointed to `/attributes/<f>` and `/relationships/<f>`, also for
  an included item, and the relationships endpoints into the document of an update: a
  client that also serves older servers reads both forms.
- A relation by a foreign key with `to_field`: its identifiers are values of that field
  (checked as such), but the relation checks (`relations_access_check`, the relationships
  endpoints) look the objects up by their primary key: such relations are not supported
  there.
- The titles and the fixed details of the errors of the core follow the language of the
  request (`ru` is translated), also the diagnostics of `ERR_FILTER` and `ERR_INCLUDE` (the
  names in them as given); the Pydantic messages (`ERR_VALIDATE`) and the messages of
  Django and Python in `ERR_FILTER` (a value that is not a number) are English.

### Several route sets of a model, read-only routes

- A second route set of a model (a projection, a public calendar) needs its own URL:
  override the classmethod `get_url_prefix()` (by default the resource path of the model,
  `/<app>/<model>`), e.g. `return '/rooms/occupancy'`, and mark the main one
  `default_route = True` (`bazis.W003`). Its own list and items are its `get_queryset`;
  the relationships, `included` and filters of the other routes use the `restrict_queryset`
  of the default route.
- A report (a narrowed list, an aggregate per object) is a route of a proxy model of the
  project (`class OpenTicket(Ticket): class Meta: proxy = True`): its type is
  `<app>.open_ticket`, its URL the resource path of the proxy, it has no create and update,
  and `get_queryset` narrows its list and items (another item is 404):

  ```python
  class OpenTicketRouteSet(JsonapiRouteBase):
      model = apps.get_model('support.OpenTicket')
      actions = ['action_list', 'action_retrieve', 'action_schema_list',
                 'action_schema_retrieve']
      fields = {None: SchemaFields(origin={'title': None, 'is_late': None})}

      def get_queryset(self):
          qs = super().get_queryset().filter(done=False)
          # who sees the tickets: the restrict_queryset of the default route of Ticket
          return TicketRouteSet.restrict_queryset(
              qs, CrudAccessAction.VIEW, user=getattr(self.inject, 'user', None))
  ```
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
    `not_gt`, `adjacent_to` with `start,end`; point: none (within 10 m), `near`, `in_bbox`
    (see Points and distances).

  Any other suffix (`__in`, `__icontains`, `__contains` on a text or number field), an
  unknown field (also after a relation, such as `customer__in`) and a calculated field that
  is not `as_filter` are an error 400 `ERR_FILTER`. `iexact`/`istartswith`/`iregex`/
  `search`/`$search` apply to every word of the value. URL-encode the value of `filter`;
  the server decodes the expression once more and every value once more, so a value with
  `&|()[]~=+%` is percent-encoded twice inside the expression; quotes are removed from
  values.
- `sort=-dt_created,number,customer__name`, `sort=location__distance(37.62,55.75)` (see
  Points and distances), `page[limit]` / `page[offset]`
  (`BAZIS_API_PAGINATION_PAGE_SIZE_MAX` caps the limit), `include=customer,items`,
  `fields[crm.order]=number,customer` (sparse fieldsets).
- `include` (retrieve, create, update) names relations of the schema of the action (an
  update also those of the create schema); a relation that is not in it (a reverse
  relation not added to `fields`, an attribute, a path `a.b`) is 400 `ERR_INCLUDE` with the
  pointer `/query/include` (with `BAZIS_FILTERS_STRICT`; without it, left out as before
  2.12). A relation in the schema that a package hides from the user (the field
  permission `disable` of bazis-permit) is left out without an error, and `included` has
  only the objects the default route of the related model shows.
- Errors are JSON:API error objects (see Errors).

### Points and distances (nearby)

A point is a `PointField` (`django.contrib.gis.db.models`) of the model, given in a request
as `<longitude>,<latitude>` (degrees of WGS 84); a distance is in meters on the sphere
(`ST_DistanceSphere`). Declare it `geography=True`: Django creates a GiST index on it, which
the `near` filter uses (a geometry point, the default, gives the same distances, cast on
every row, without the index). Never two `FloatField`s with
`ST_MakePoint` per row: no index, and the filter and the sorting below are not available.

```python
from django.contrib.gis.db import models

class Site(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField(_('Name'), max_length=255)
    location = models.PointField(_('Location'), geography=True, null=True, blank=True)
```

The API shows it as GeoJSON (`{"type": "Point", "coordinates": [lon, lat]}`) and takes it so
on a write. On a route whose LIST schema has `location`:

- `filter=location__near=37.62,55.75,5km`: within 5 km (`500` and `500m` are meters; 100 m
  without a distance); `filter=location=37.62,55.75`: within 10 m;
  `filter=location__in_bbox=<lon min>,<lat min>,<lon max>,<lat max>`;
- `sort=location__distance(37.62,55.75)`: the nearest first (`-location__distance(...)` the
  farthest first), the objects without a point last; other terms follow
  (`sort=location__distance(37.62,55.75),name`).

The nearby list of a mobile client: the point comes from the client (the geolocation of the
browser) in the request, nothing is stored about the user:
`?filter=location__near=37.62,55.75,10km&sort=location__distance(37.62,55.75)`. The sorting
computes the distance of every object the filter leaves: bound it with `near` on a large
table. Like any key, the point field must be in the LIST schema of the route (400
`ERR_FILTER` otherwise, pointer `/query/filter` or `/query/sort`); a malformed point or
distance is 400 too. The responses carry no distance: it depends on the request, not on the
resource, and the client has both points to show it (the haversine formula gives the same
value). A distance in the code (an annotation, a calculated field, a distance to a point of
another row): `point_distance(field, point)` and `point_within(field, point, meters)` of
`bazis.core.utils.geo` (`field` is `Site._meta.get_field('location')`, `point` a GEOS point
(`parse_point('37.62,55.75')`) or an expression of a point such as a `Subquery` of a point
field).

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
- The database connection of a thread other than the main one (the AnyIO worker threads
  that run the sync endpoints and dependencies, a thread a package starts) is closed by the
  core when the thread ends. While the thread lives it keeps its connection between the
  requests for `CONN_MAX_AGE`; on every request (a middleware of the application, and the
  endpoints of the route sets in their own thread) `close_old_connections` of
  `bazis.core.utils.orm` closes it once it is obsolete or broken and has it checked again
  before its next use (`CONN_HEALTH_CHECKS`). A thread that runs a loop of jobs calls
  `close_old_connections` between the jobs. Do not close the connections in the
  endpoints, and do not hand a connection to another thread.
- Do not access `settings.<dynamic setting>` at import time: dynamic settings are read from
  the database (constance).
- Do not edit generated schemas by hand; change the model or `fields` of the route.
