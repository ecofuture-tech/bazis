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
  the declared roles, workflows and schedules against the rows), against `default` when it
  can be reached; otherwise they are skipped with the info `bazis.database`, so a warning-free
  doctor without the database says nothing about the data (`SILENCED_SYSTEM_CHECKS`
  silences the info). `--database` (repeatable) names the databases, and one that cannot
  be reached is an error. PostgreSQL is probed with a connect timeout of 5 seconds.

With bazis-mcp installed, the MCP server `bazis-mcp` gives the same facts and checks and the
guides of all Bazis packages, also the ones not installed.

### The sections

Read a section with `package_guide("bazis", "<section>")` when the step at hand needs it;
`guide_search` finds the part of a section that answers a question. An app needs Project
layout, Models, Routes and Rules; the other sections when the product has what they
cover.

| Section | Read it when |
|---|---|
| Project layout | you create a project or an app: its files, the media and static files, the size of a request body, the `BS_*` settings and `BS_INSTALLED_APPS`, the dynamic settings, the translations (`bazis_messages`), the language of a request |
| Models | you write a model: the mixins and the resource type, `URLField`, the declarations in the code, the triggers (pgtrigger) and `migrate`, `UniqNumberMixin`, data named in every language, callable defaults |
| Invariants of the items | a rule that every write of an item must keep: `validate_item` and `ItemChanges`, `defer_validate_item`, limits and unique values under concurrent requests (`lock_on_write`, `set_item(with_lock=True)`, tests with `parallel`), no overlapping intervals of a participant |
| Calculated fields | a field the query of a route computes (`calc_property`, `FieldAnnotate`, `FieldDynamic`, a subquery, the user of the request), or one computed from the item itself |
| Routes | you write a route set: its schemas (`fields`, `SchemaFields`), `restrict_queryset`, the default route, the routers, a second route set of a model, read-only routes and reports |
| Custom routes and actions | an endpoint that is no CRUD: `@http_get`/`@http_post`, the models of its body and response, an answer that is a file with its meta (`file_answer`, `file_meta`), `public` and `access_action`, `route_declare`, the errors in the OpenAPI, the rate limits (`throttle`), the code around every route (`BAZIS_MIDDLEWARES`, `<action>__before`/`__after`) |
| Writes and errors | the hooks of the create, the update and the relationships endpoints and their order, the errors the API answers (`ValidationError`, `JsonApiBazisException`, 409 `ERR_CONFLICT`) and their pointers |
| API conventions | a client builds a request: `filter` and its lookups, `sort`, `search`, `include`, the pages, sparse fieldsets, the points and the distances (`near`, `distance`) |
| E-mail | the product sends mail: the dynamic SMTP settings, the sender, the console backend in development, mail from a task |
| Rules | before you write the code of a project, once: what every model, route and custom endpoint must respect |

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

### Media and static files

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

### Size of a request body

`BS_BAZIS_API_MAX_BODY_SIZE` (bytes, `0` - no limit, the default; not dynamic; bazis 2.22)
refuses a larger request with 413 `ERR_BODY_TOO_LARGE` (JSON:API, translated, with the
headers of CORS) in the application of Bazis: by its `Content-Length` before the routes run,
a chunked body as soon as the bytes received exceed it, so no route reads or parses a larger
body; a body that exceeds it once a response has started (a streaming one) ends the request
as a disconnection of the client. The middlewares the project or a package adds to the
application afterwards run outside it and are not limited: the `AsyncRequestMiddleware` of
bazis-async-request reads the whole body before it, answers 202, and its task ends with
the 413. With such a middleware the limit of the reverse proxy is the one that holds. Set
it in production above the largest request of the project (with bazis-uploadable at least
`BAZIS_FILE_UPLOAD_MAX_SIZE` plus the multipart overhead), and limit the body on the reverse
proxy as well (`client_max_body_size` of nginx). `DATA_UPLOAD_MAX_MEMORY_SIZE` of Django
applies to the admin only.

### Settings: `BS_*`

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
A project's own `conf.py` may redeclare a setting of the core or of a package with another
default: the default of a field comes from the first conf in the order project, core,
packages, and a `BS_*` variable beats every default. `BS_BAZIS_APPS` (or `BS_BAZIS_CONFIG_APPS`)
is only an explicit override: the exact list of
the packages to load the settings from. Leave it unset; `'[]'` turns off the settings of all Bazis packages, also
of the ones the project uses (`bazis_doctor` warns, `bazis.W002`). Requirements:
PostgreSQL with PostGIS and Redis (`BS_CACHES__DEFAULT__LOCATION`): the default cache must
be Redis (django-redis), other backends lack `delete_pattern` (`bazis.E001`). `DEBUG` is
true by default: set `BS_DEBUG=false` and `BS_SECRET_KEY` (required without DEBUG) in
production, and `BS_ALLOWED_HOSTS`, which is `['*']` by default (`bazis.W001`).
The settings are built before Django starts, so the `conf.py` modules are found by their
paths: only `conf.py` and the packages it sits in are imported, never the other subpackages
of a Bazis package. Still keep the `__init__.py` of a package light (no models, no
`bazis.core` imports) if it holds a `conf.py`.

A dynamic setting (editable in the admin: the page Constance; the throttle rates, the mail,
`DEFAULT_FROM_EMAIL`, the page sizes) is read from the database on every use, and its
`BS_*` variable is its default: the setting follows the variable until a value is set in
the admin, with `manage.py constance set <NAME> <value>` or `config.<NAME> = ...`; a set
value wins over the variable (`manage.py constance list` shows the values). Bazis 2.16 no longer
saves the default when a setting is read: before, the first read saved it, and a variable
set later had no effect. A value equal to the default is not saved either (it is the value
already): to keep a value whatever the variable says later, keep it in the `BS_*`
variable, the source of the value then, or set it in the admin while it differs from the
default. A database used before 2.16 has the defaults of its first reads saved: to let a
setting follow its variable again, delete its saved value, `manage.py shell -c "from
constance.models import Constance; Constance.objects.filter(key__in=['DEFAULT_FROM_EMAIL']).delete()"`
(the keys with `CONSTANCE_DATABASE_PREFIX`; with `CONSTANCE_DATABASE_CACHE_BACKEND` the
cached value lasts until it expires).

### Translations: `bazis_messages`

Translations: the core puts into `LOCALE_PATHS` the `locale` directory of the project
(`<BASE_DIR>/locale`), then those of the installed apps in the order of `INSTALLED_APPS`
(the apps of the project included), then those of the Bazis packages that are not installed
(a project uses the abstract models of bazis-users without installing it) by name. Other
libraries that are not apps are not included. When two catalogs translate the same msgid,
the first one wins, in every process: the list depends only on the settings
(`bazis_doctor` warns when two Bazis packages differ, `bazis.W004`). To change a
translation of a package (also to settle a `bazis.W004`), translate the msgid in the
project's `locale`, or give the field its own title (`verbose_name` of the model field, or
`SchemaField(title=...)` in `fields` of the route). A msgid of a package is not in the code
of the project, and `bazis_messages make` (below) drops the entries that are not: declare
it in a module of the project, `<project>/translations.py`, with `gettext_noop` (the text is
not translated there, makemessages extracts it), then translate it through `bazis_messages`
like the other texts; the catalog of the project comes first and wins:

```python
from django.utils.translation import gettext_noop

# the msgids of the packages that the project translates itself (bazis.W004)
PACKAGE_MSGIDS = [
    gettext_noop('Name'),
]
```
 Write the msgids in English (`gettext_lazy`): English needs no catalog, every
other language of `LANGUAGES` does (`bazis.W005` lists the Bazis packages left untranslated).

The catalogs of the project (`<BASE_DIR>/locale` and the `locale` directories of its apps,
never those of the installed packages) are made, filled and compiled by
`python manage.py bazis_messages` (GNU gettext required); do not write a script that edits
`.po` files (makemessages run elsewhere than BASE_DIR, or before `<BASE_DIR>/locale`
exists, writes into the first catalog of `LOCALE_PATHS`, of an installed package):

- `make`: makemessages from BASE_DIR for the languages of `LANGUAGES` but English
  (`-l ru` to choose), without the obsolete (`#~`) entries, ignoring the hidden
  directories (`.venv`, `.scratch`) and `node_modules` anywhere, `MEDIA_ROOT`,
  `STATIC_ROOT`, a virtual environment at the top of BASE_DIR (its `pyvenv.cfg`, whatever
  its name), and `venv`, `frontend`, `static`, `media`, `build`, `dist` there unless they
  are Python packages (an app named `media` is translated, as a
  directory of such a name deeper in the tree); `-i <glob>` adds a pattern of
  makemessages; then prints the status;
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

### Languages of a request

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
is then in the active language too, with the labels of the Django choices (`enumDict`) as
in the OpenAPI (bazis 2.22). Every HTTP response has `Vary: Accept-Language`. Keep titles lazy (`gettext_lazy`,
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
- A `URLField` is checked on the API (the routes do not run the validators of the
  fields): a URL of the schemes of its `URLValidator` (http, https, ftp, ftps;
  `validators=[URLValidator(schemes=['https'])]` narrows them, Django runs every validator
  of the field) within its `max_length`, or `''`; `javascript:`, `data:` or a URL without
  a scheme (`example.com`) is 422 `ERR_VALIDATE` at its attribute. Other schemes
  (`mailto`) need a subclass of `URLField` with its own `default_validators`;
  `validators=` with no scheme in common with the default one is `ImproperlyConfigured`
  at the start, naming the field. The value is stored normalized (`https://example.com`
  becomes `https://example.com/`, the scheme and the host lowercase). Its JSON schema,
  of the requests and of the responses, is a flat `anyOf` of
  `{type: string, format: uri, minLength: 1, maxLength}` and
  `{type: string, maxLength: 0}` (plus `{type: null}` when it is nullable): the contract
  of the values written now. A response shows the stored value as it is, so a value
  stored before bazis 2.16 that is not a URL is still read, and refused when it is
  written again: fix such rows by a data migration.

### Declarations in the code (`bazis.core.declare`)

- Declarations in the code (for package authors): `bazis.core.declare` holds what
  bazis-permit (`roles.py`), bazis-statusy (`workflow.py`) and bazis-bg (`schedules.py`)
  share to apply `<app>/<module>.py` on `migrate`: `discover` the modules,
  `apply_after_migrate` (after all migrations, in a transaction under the shared advisory
  `lock`), `ManagedSync` (create, update, or take over an unmarked object of the same `slug`
  with a warning; the model has a unique `slug` and a `managed` flag), `managed_orphans`
  (the managed objects no longer declared; each package decides their fate), and
  `ManagedAdminMixin` (`bazis.core.admin_abstract`, declared objects read-only).

### Triggers of the models (pgtrigger)

- The core (`dt_created`/`dt_updated`), the packages (the current role of bazis-permit) and
  the projects (`Meta.triggers` of a model, `pgtrigger.Trigger`) keep rules in PostgreSQL
  triggers. They are not in the migrations: `migrate` installs the ones the database lacks
  or has outdated (changed in the code) once all the migrations of the database are
  applied (bazis 2.16; before, only `manage.py pgtrigger install` did, and the databases
  of the projects lacked them while the tests had them). A `migrate` with nothing to
  change runs no DDL; a `migrate` to an earlier migration and `flush` install nothing.
  Each trigger is installed in a short transaction that waits for the lock of its table
  at most `BS_BAZIS_TRIGGERS_LOCK_TIMEOUT` seconds (5; 0 - unlimited): behind a long
  transaction on the table `migrate` fails after its migrations, naming the trigger; run
  it again.
- `migrate` never removes a trigger: one no model declares any more (renamed, its model
  deleted) or of another project in the same database keeps running. `bazis_doctor`
  warns of the missing or outdated triggers and of the ones no model declares
  (`bazis.W008`): `manage.py migrate` installs the first (`manage.py pgtrigger install
  <uri>` one of them); remove one of the others that is not of another project by its
  name, `DROP TRIGGER <name> ON <table>` and `DROP FUNCTION <name>()` (`manage.py dbshell`);
  `manage.py pgtrigger ls` lists them all. `manage.py pgtrigger prune`, and `install` and
  `uninstall` without a URI, remove every trigger of pgtrigger that no model declares, also
  the ones of another project that shares the database: name the triggers
  (`app_label.Model:name`).
- The triggers stay installed while the next migrations run, as the code of their
  version: they fire on the writes of a data migration (`RunPython`, `RunSQL`), and one
  that reads a column a migration removes or renames fails those writes (a condition of a
  trigger on the column even refuses the removal). Run such a migration after `manage.py
  pgtrigger uninstall <uri>` of the affected triggers; the `migrate` that follows installs
  them again.
- Deploy: run `migrate` as a step of its own before the processes of the new version
  start, never from the processes of the old version once the new one migrated: an old
  `migrate` sees the triggers of the new version as changed and installs its own again.

### Numbers: `UniqNumberMixin`

- Numbers: `UniqNumberMixin` (`bazis.core.models_abstract`) gives the item `uniq_number`, the
  next value of a database sequence (django-sequences, installed by the core) on its first
  save, and the property `number` (its string; override it to format, calling `super()`).
  The sequence is named by `NUMBER_LABEL` (default: the resource label of the model; give
  several models one label to share the numbering). Show it with
  `include={'number': None}`, and exclude `uniq_number` from the create and update schemas
  (it is an ordinary integer field there).

### Data named in every language

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
  (`include={'name_en': None, 'name_ru': None}`). A query of the project by such a field
  takes its column in the active language from `translated_name(model, 'name')`
  (`bazis.core.utils.query_complex`).

### Callable defaults of the fields

- A callable default of a model field (`auto_now`, `timezone.now`, `uuid.uuid4`, `dict`, a
  database lookup) is never evaluated by the schemas, neither when they are built nor when
  a request or a response is validated: the field is optional, without a `default` in the
  OpenAPI, and an omitted field gets the default of the model on save (only the attributes
  sent by the client are written). Static defaults (`True`, `'new'`) stay in the OpenAPI.
  The generated OpenAPI must not depend on the process or the time (it is hashed to detect a
  stale frontend contract): do not put random or time-based values into schemas.

## Invariants of the items

### Invariants of an item: `validate_item`

- Invariants: override `validate_item(self, changes)` and raise a Django
  `ValidationError` (a dict by field) to refuse a write:

  ```python
  from django.core.exceptions import ValidationError
  from django.utils.translation import gettext_lazy as _

  class Booking(DtMixin, UuidMixin, JsonApiMixin):
      # every write of a booking locks its room first, until the commit: the bookings of
      # a room are checked one after the other (Invariants under concurrent requests)
      lock_on_write = ('room',)

      def validate_item(self, changes):
          if changes.is_new or changes.fields & {'room', 'dt_start', 'dt_end'}:
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

### Invariants under concurrent requests

- Invariants under concurrent requests ("no more than N per parent", "one open per
  parent", "an e-mail once per parent", a number in the parent): a check by `count()`
  passes in every parallel request (each sees only the committed rows) unless the requests
  are serialized. Serialize the writes on the parent row: name the foreign key in
  `lock_on_write`, count in `validate_item`, and keep a `UniqueConstraint` as the barrier
  that no code path can bypass:

  ```python
  class Application(DtMixin, UuidMixin, JsonApiMixin):
      lock_on_write = ('vacancy',)

      vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE,
                                  related_name='applications')
      email = models.EmailField()

      class Meta:
          constraints = [models.UniqueConstraint(fields=['vacancy', 'email'],
                                                 name='application_email_uniq')]

      def validate_item(self, changes):
          if changes.is_new or 'vacancy' in changes.fields:
              # under the lock of the vacancy; the item is in the database already: counted
              if self.vacancy.applications.count() > self.vacancy.max_applications:
                  raise ValidationError({'vacancy': _('No more applications')})
  ```

  `lock_on_write` (a class attribute of `JsonApiMixin`: names of foreign keys) locks the
  rows they point to (`SELECT ... FOR NO KEY UPDATE`, by the current values: the new
  parent when the item moves; an empty key locks nothing) before every write of an item,
  whatever writes it: the create and update routes, the actions, the admin, scripts,
  commands, background tasks, the transits of bazis-statusy (every `save()`), and the
  items a reverse foreign key links (the relationships endpoints, the create and the
  update of the parent with the relation: they are saved one by one then, not by one bulk
  update). The lock holds until the commit: the next write under the same parent waits,
  then its `validate_item` counts the committed row. Do not lock the parent again in
  `validate_item`: the lock is held. Not covered: `QuerySet.update()`, `bulk_create()`,
  `bulk_update()`, raw SQL, `add()`/`set()` of a many-to-many manager (the rows of the
  `through` model are written without `save()`) and the deletion (it does not lock the
  parent: a deletion does not break a limit counted in `validate_item`).

  The order of the locks matters as much as the locks: the parent before the item,
  everywhere. An action that locks the parent itself and then creates the item
  (`Vacancy.objects.select_for_update(no_key=True).get(pk=data.vacancy)`, or
  `self.set_item(item_id, with_lock=True)` on the route of the parent) takes them in the
  order of the create route. Locking the parent only in `validate_item`, which runs after
  the insert, inverts it: such an action and a create of the same unique value deadlock,
  and PostgreSQL aborts one of them (409 `ERR_CONFLICT` with `meta.retry`, see Errors).
  `set_item(item_id, with_lock=True)` on the route of a model with `lock_on_write` locks
  its parents before the item (bazis 2.16): an action of the item (a write action that
  bazis-permit checks with `access_action`, a transit of bazis-statusy) runs in the order
  of a create and of a write of the parent that saves its items. An action that locks a
  row of the item directly (`Model.objects.select_for_update().get()`), past `set_item`,
  locks the parent first itself.

- A number in the parent is taken before the write, so `save()` locks the parent before
  it computes the number (the lock of `lock_on_write` that follows is the same lock: it
  does not wait):

  ```python
  from django.db.models import Max

  class Attempt(DtMixin, UuidMixin, JsonApiMixin):
      lock_on_write = ('assignment',)

      assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE,
                                     related_name='attempts')
      number = models.PositiveIntegerField(editable=False)

      class Meta:
          constraints = [models.UniqueConstraint(fields=['assignment', 'number'],
                                                 name='attempt_number_uniq')]

      def save(self, *args, **kwargs):
          if self._state.adding and not self.number:
              Assignment.objects.select_for_update(no_key=True).get(pk=self.assignment_id)
              last = self.assignment.attempts.aggregate(m=Max('number'))['m'] or 0
              self.number = last + 1
          super().save(*args, **kwargs)

      def validate_item(self, changes):
          if changes.is_new:
              if self.assignment.attempts.count() > self.assignment.max_attempts:
                  raise ValidationError({'assignment': _('No attempts left')})
  ```

- A custom action that changes its item takes it with `self.set_item(item_id,
  with_lock=True)` (`SELECT ... FOR NO KEY UPDATE`: parallel calls run one after the other)
  and checks its state after the lock (a submit of an attempt that is no longer open is
  refused, not graded twice). A write the constraint still refuses (a race the code missed,
  two parallel creates of a unique value) answers 409 `ERR_CONFLICT`, never a 500 (see
  Errors). An action whose item bazis-permit already took (`access_action`) has it in
  `self.item`: locked for POST/PUT/PATCH/DELETE (`set_item(item_id, with_lock=True)`
  returns it without another query), unlocked for GET (`set_item(..., with_lock=True)`
  reads it again, locked); with `lock_on_write` its parents were locked before it. Take
  the locks in one order everywhere, the parent before the item: an action of a model
  without `lock_on_write` that holds its item and then locks the parent (or another row)
  must not race a write that locks the same parent first and then the item — declare the
  parent in `lock_on_write`, or keep the item action from locking the parent. A deadlock
  the code did not avoid (also an item moved to another parent while an action of it
  waits for the lock) answers 409 `ERR_CONFLICT` with `meta.retry` (the client may send
  the request again); it is a safety net, not the design.

- Test every such invariant with parallel requests: `parallel(count, func)` or
  `parallel([f1, f2, ...])` of bazis-test-utils runs the calls at once in threads and
  returns their results in order (its guide, "Parallel requests"). The invariant holds and
  the answers are 201, 409 or 422, never 500; also for two paths that create the same item
  (an action and the create route):

  ```python
  from bazis_test_utils.utils import get_api_client, parallel

  @pytest.mark.django_db(transaction=True)  # the endpoints see only committed data
  def test_no_more_than_3_attempts(sample_app, assignment):
      def attempt():
          return get_api_client(sample_app).post('/api/v1/school/attempt/', json_data={
              'data': {'type': 'school.attempt', 'relationships': {'assignment': {
                  'data': {'type': 'school.assignment', 'id': str(assignment.pk)}}}},
          }).status_code

      assert sorted(parallel(6, attempt)) == [201] * 3 + [422] * 3
  ```

- No overlapping intervals of a participant ("an interviewer has no two interviews at the
  same time", "a host no two sessions"): the rows of a many-to-many relation with a
  `through` model hold the interval of their parent, and an exclusion constraint of the
  through model refuses two overlapping intervals of one participant, whatever writes them
  (the create and update of the parent, the relationships endpoint, the admin, parallel
  requests). `set()` writes the rows of the through model without `save()`, so triggers
  fill the interval (the triggers are installed by `migrate`, see Triggers of the models
  in Models):

  ```python
  import pgtrigger
  from django.contrib.postgres.constraints import ExclusionConstraint
  from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators

  class Session(DtMixin, UuidMixin, JsonApiMixin):
      dt_start = models.DateTimeField(_('Start'))
      dt_end = models.DateTimeField(_('End'))
      # optional on the create: blank=True
      hosts = models.ManyToManyField(Person, through='SessionHost', blank=True,
                                     related_name='sessions')

      class Meta:
          triggers = [pgtrigger.Trigger(   # the periods follow the time of the session
              name='session_period_sync', when=pgtrigger.After, operation=pgtrigger.Update,
              condition=pgtrigger.AnyChange('dt_start', 'dt_end'),
              func='UPDATE events_sessionhost SET period = tstzrange(NEW.dt_start, NEW.dt_end) '
                   'WHERE session_id = NEW.id; RETURN NULL;')]

  class SessionHost(InitialBase):
      session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='+')
      host = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='+')
      period = DateTimeRangeField(editable=False)   # filled by the trigger

      class Meta:
          constraints = [
              models.UniqueConstraint(fields=['session', 'host'], name='session_host_uniq'),
              ExclusionConstraint(name='session_host_no_overlap', expressions=[
                  ('host', RangeOperators.EQUAL), ('period', RangeOperators.OVERLAPS)]),
          ]
          triggers = [pgtrigger.Trigger(
              name='session_host_period', when=pgtrigger.Before,
              operation=pgtrigger.Insert | pgtrigger.Update,
              func='NEW.period := (SELECT tstzrange(dt_start, dt_end) FROM events_session '
                   'WHERE id = NEW.session_id); RETURN NEW;')]
  ```

  The migration that creates them starts with `BtreeGistExtension()`
  (`django.contrib.postgres.operations`: the equality of a key in a GiST index). The SQL of
  the triggers names the tables (`<app>_<model>`). The relation is written like any
  many-to-many relation: in the create and the update of the parent (optional with
  `blank=True`, required otherwise) and by its relationships endpoint; its reverse side
  (`person.sessions`) is read-only. An overlap answers 409 `ERR_CONFLICT` without a
  pointer (see Errors). For a 422 at the field, check the overlap in `validate_item` of the
  parent under a lock of the participants (`pg_advisory_xact_lock`) and make the constraint
  `deferrable=models.Deferrable.DEFERRED`, so that the check answers before the constraint
  (checked at the commit). The interval of the through rows is the barrier: never compute
  it in `save()` of the through model, which `set()` does not call.

## Calculated fields

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
          return self.tickets.filter(done=False).count()
  ```

  The query of a route sets the attribute (by `alias`) on the item, so the method is not
  called there; it is called by the other reads (the admin, the shell, the code of the
  project, an item created or locked without the query of the route): compute the value
  there. Never `return self.<alias>` when the alias is the name of the property: the
  method calls itself again (`RecursionError`, a 500).

  `FieldAnnotate(source, query)`: an expression of the row. `FieldDynamic(source=<relation>,
  ...)`: with `func` (`'Count'`, `'Sum'`, ...; `source` may end with the field,
  `tickets__hours`) a subquery aggregate over the related objects filtered by `query` (the
  `Meta.ordering` of the related model is dropped there, bazis 2.12); with `fields=[...]`
  a list of dicts of the related objects (`order_by`, `slice`); without them the related objects
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
          return Request.objects.filter(department=self, status_id='approved').aggregate(
              total=Sum('amount'))['total']
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
      return None  # the user of the request is known only to the query of a route
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
- A value computed from the fields of the item itself (a full name, a label), with nothing
  to fetch: `@calc_property([])` (or a plain `@property`) with the return annotation,
  added to the schema the same way (`include={'full_name': None}`; read-only, a write
  ignores it). It is computed for each item of a list, an item, the response of a write
  and a sparse fieldset (`fields[app.model]=full_name`); `calc_property([])` keeps the
  value on the item (a cached property), a `@property` computes it on each read. It is
  not a filter, a sort or a search field: for that, an annotation (`FieldAnnotate`,
  `as_filter=True`).

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
  A forward relation (a foreign key, a many-to-many field, also with a `through` model)
  is required in the create schema unless its model field has `blank=True`, `null=True`
  or a default.
- A create or an update names only the attributes and relationships of the schema of its
  action: any other (excluded by `fields`, hidden by a field permission of bazis-permit,
  unknown) is 422 `ERR_VALIDATE` (bazis 2.12) with the title `extra_forbidden` and the
  pointer `/data/attributes/<f>` (`/data/relationships/<f>`, `/included/<i>/...`); a field of the
  schema that is read-only there (calculated fields, `SchemaField(read_only=True)`, the
  permission `readonly`) is ignored. A text field (`CharField`, `TextField`) without
  `blank=True` refuses an empty value or one of only whitespace (422 `ERR_VALIDATE` at the
  field, bazis 2.12), as the forms of Django; the value is stored as sent. A field the
  client may leave empty is `blank=True`. The responses are not checked for blank values,
  and `save()` in the code does not run the schemas.
  A field with `choices` accepts only their values (422 `ERR_VALIDATE` at the field,
  "Value 'x' is not a valid choice", bazis 2.18): the `enum` its OpenAPI schema shows,
  so the keys of the choices (also of callable and grouped ones, not the labels or the
  names of the groups), every element of an array field. A value is a choice as sent, as
  the schema type converts it, or matching a key converted by that type (bazis 2.20): a
  type registered in `TYPES_DJANGO_TO_SCHEMA` that makes an object of a code accepts the
  codes, a Decimal, UUID or date key is sent as the OpenAPI shows it, `"2"` is a choice of
  integers; a value the type refuses is refused as not a choice. Null and empty values
  are left to the checks of `null` and `blank` (an empty value of a `blank=True` field
  need not be a choice). The choices are read when the schema is built, and a callable
  one is called then; the responses and `save()` in the code do not check them.
  A relation read-only there (`SchemaField(read_only=True)`, the field permission
  `readonly` of bazis-permit) is ignored by an update, and the relationships endpoints
  refuse it as a relation that is not in the schema: 403 `ERR_RELATIONSHIP_READONLY` with
  `source.parameter` `/related_field_name`.

### Fields of a route

`fields = {<action or None>: SchemaFields(...)}` (`None`: every action). By default a schema
has the attributes and the forward relations of the model, without the internal columns a
package adds to it (`Model.get_fields_hidden()`, such as the selector arrays
`autogen_<field>_selectors` of bazis-permit): a route has one only when it names it in
`include` or `origin`. `origin={...}` replaces them
with the listed fields (a projection), `include={...}` adds fields (reverse relations,
calculated fields, a `SchemaField` that overrides one), `exclude={...}` removes fields and
wins over `include`. The entries of an action are read along the MRO of the route, the
parent classes first, and in each class its `None` entry, then its entry of the action:
`include` and `exclude` add up, the last `origin` wins (the action entry of the route,
else its `None` entry, else the entries of the parents; so a `None` entry of a child
overrides an action entry of its parent). `is_inherit=False` on the entry of an action
leaves out the `None` entry of the same class only.

`SchemaField(source=...)` names the attribute of the model a field shows (by default its
own name). A callable source, `source(route_cls, item) -> <type>`, computes the value of
the field (also one named as a column, which it replaces): the field is read-only, does not
filter or order, and its type is the return annotation (bazis 2.19.1; before, the schema
failed with a `TypeError`). The function must be of the module level: the schemas are
named by a hash of their fields that takes it by its qualified name, and a lambda or a
nested function gives names that change between processes (the OpenAPI is not stable).

### The visibility of the objects for the other routes: `restrict_queryset`

- Visibility of the objects of a model for the other routes: override the classmethod
  `restrict_queryset(qs, access_action, user=None, **kwargs)` of `RestrictedQsRouteMixin`
  (`bazis.core.routes_abstract.jsonapi`) in the default route of the model (the core
  calls it on the class with `user`, the `inject.user` of the calling route: None if the
  route has no user, or anonymous; never raise for them, return what a user without
  authentication may see, e.g. `qs.none()`, or fall back to a request-level user of the
  package; the route of the request is `JsonApiMixin.CTX_ROUTE.get()`; accept
  `**kwargs`). A relationship of a created or changed item (create, update, the
  relationships endpoints) links only the objects it returns for `view`, a reverse
  relationship only the objects it returns for `change` (their foreign key changes; the
  objects it unlinks for `delete` when the foreign key cannot be null: they are deleted),
  both for the objects whose link changes; otherwise 403 `ERR_RELATION_ACCESS` (pointers: see
  Errors). The core asks for the objects that get linked (not the ones a reverse
  relationship unlinks) with `link=True`: an override may return
  fewer then, the objects the user may link (e.g. bazis-uploadable: only his own files,
  though he sees more), and a visible object it leaves out is 422 `ERR_RELATION_LINK`
  (same pointers). `included` shows only the visible objects (the
  relationship keeps the identifiers), and the filter, sorting and search of the other
  routes reach only the visible objects through a relation. The objects a relationship
  links of a model whose default route does not override `restrict_queryset` (or that has
  no route) are only looked up (one query per relationship): one that does not exist is
  422 `ERR_VALIDATE` at its identifier (bazis 2.16; a 500 at the commit before). A missing
  object of a model whose route restricts its objects is 403 `ERR_RELATION_ACCESS`, as a
  hidden one (its existence is not told). `relation_targets_check = False` turns the check
  off for the relationships of a route, the lookup too, but for a foreign key with
  `to_field`: its write looks the object up by the primary key to store its `to_field`, and
  a primary key of no object is still refused: 422 `ERR_VALIDATE` at its identifier in a
  create or an update, 400 `ERR_REQUEST` at the relationships endpoints (as for any
  foreign key).
  The route's own list and item do not use `restrict_queryset` by themselves: apply it in
  `get_queryset` too. Who calls it: the core (`route_restrict_queryset(model)` of
  `bazis.core.routes_abstract.jsonapi.mixins`) for the relationship targets of the writes,
  `included` and the filter, sort and search through a relation; bazis-permit implements it from the permissions and
  restricts the items of its routes with it; the core never applies it to the list of a
  route by itself.

### The default route of a model

- The default route of a model (`Model.get_default_route()`) is the last defined route
  class of the model (abstract ones never), unless one declares `default_route = True` in
  its class body (not inherited). With several route sets of a model that restrict its
  objects differently, declare it (`bazis_doctor` warns, `bazis.W003`). A route set no
  router registers counts too: imported for another reason after the routed one, it
  becomes the default route (`bazis.W010` when it restricts the objects otherwise and does
  not declare `default_route = True`).

### Registering the route sets

- Register: `router = BazisRouter(tags=['CRM'])`, `router.register(OrderRouteSet.as_router())`
  in `<app>/router.py`; the root router (`BazisRouter(prefix='/api/v1')`) registers the app
  routers by module name: `router.register('crm.router')` (its `router`). `register` also
  takes a router object (`router.register(files_router)`, a `BazisRouter`); the prefix of
  `as_router()` is `get_url_prefix()` of the route class.

### Several route sets of a model, read-only routes

- A second route set of a model (a projection, a public calendar) needs its own URL:
  override the classmethod `get_url_prefix()` (by default the resource path of the model,
  `/<app>/<model>`), e.g. `return '/rooms/occupancy'`, and mark the main one
  `default_route = True` (`bazis.W003`). Its own list and items are its `get_queryset`;
  the relationships, `included` and filters of the other routes use the `restrict_queryset`
  of the default route.
- A total or a grouped count of a list (a dashboard tile, a chart by month) needs no
  route: `meta=aggregates` of the list (API conventions).
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
  A route set without `action_list` (a file upload with `create` and `retrieve`) is fine:
  `route_filter_fields/` of a route with a relation to it lists the relation with
  `py_type` `unknown` (bazis 2.19; before, the endpoint answered 500), as for a relation
  to a model without a route.

## Custom routes and actions

- Custom routes: `@http_get('/{item_id}/card/', kind=RouteKind.ITEM)` (decorators
  `http_get`, `http_post`, `http_put`, `http_patch`, `http_delete` from
  `bazis.core.routes_abstract.initial`, `RouteKind` from `bazis.core.schemas.enums`). The
  decorator takes the path, then `inject_tags` (the injections of an action, e.g.
  `[CrudApiAction.LIST]` for `self.inject.filtering`), `response_model` (a Pydantic model
  of the response), `kind`, `public` and `access_action` (who may call an action, below),
  and the arguments of FastAPI (`status_code`, `responses`, `summary`, `dependencies`,
  ...). The method is the endpoint: its parameters other than `self` and
  `**kwargs` are the parameters of FastAPI (a path parameter `item_id: str`, a Pydantic
  model the JSON body, a typed name a query parameter); `self.inject.user` is the user
  with bazis-users; `self.set_item(item_id)` loads the item the route shows (404
  otherwise) and `self.item` is it then. An id in the body or the query of an action is
  typed as the primary key of its model (`UUID` for `UuidMixin`, `int` otherwise), never
  `str`: the request schema answers a malformed one 422 `ERR_VALIDATE` before any lookup
  (`filter(pk='not-a-uuid')` raises a Django `ValidationError`, see Errors):

  ```python
  class ExportRequest(BaseModel):
      date_from: date
      date_to: date
      site: UUID | None = None  # the id of a Site, typed as its key

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

  A variant of a body is typed by the `TextChoices` / `IntegerChoices` of the model, not by
  a `Literal` or an own `Enum`: a field of such a type is an `enum` in the OpenAPI schema
  of the body, and its labels go as `enumDict` (value to the label in the language of the
  generation, the same key as for the `choices` of a model field; bazis 2.21; also in the
  JSON schemas of `TranslatedJsonSchema`, such as the payload of a transit of bazis-statusy,
  bazis 2.22), so a client shows the labels of the model without a route that lists them.
  A `Literal` and an `Enum` that is not a Django `Choices` have no labels:

  ```python
  class SubmitRequest(BaseModel):
      work_type: Order.WorkType  # TextChoices of the model: enum with enumDict
  ```

  A required text of a body (a reason, a comment) strips the whitespace before its length
  is checked: `reason: Annotated[str, StringConstraints(strip_whitespace=True,
  min_length=1)]` (pydantic), since `Field(min_length=1)` accepts `"   "`; test it with a
  text of only spaces (422). The attributes of a JSON:API document already refuse such a
  text in a field that is not `blank`, and the payloads of the transits of bazis-statusy
  are stripped.

  An action that answers a file declares the class of its answer with the media type (the
  OpenAPI then shows a file, not JSON) and returns `file_answer(content, filename,
  media_type, meta=None)` (`bazis.core.routes_abstract.initial`, bazis 2.25): the content,
  `Content-Disposition: attachment` with the name (`filename*`, percent-encoded, for a name
  that is not ASCII or has control characters). What the client shows next to the file (the number of rows, a total) is its meta:
  a small flat Pydantic model declared with `file_meta=` of the decorator, which puts the
  header `X-Bazis-Meta` with the JSON schema of the model as it is sent (with its computed
  fields) in the OpenAPI answer of the route (`responses=` of the route win). Its fields are
  scalars (`str`, `int`, `float`, `bool`, None, dates): an enum or a nested model is a
  `ValueError` of the decorator (type an enum as `str`). It is passed to `file_answer`,
  which sends it as JSON in ASCII in that header (at most 4096 characters, else
  `ValueError`). CORS lets a client of another origin (`CSRF_TRUSTED_ORIGINS`) read both
  headers; a reverse proxy must pass them. bazis-front shows the properties of the meta in the result of the form (`{count}`):

  ```python
  class XlsxResponse(Response):  # fastapi.responses
      media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

  class ExportMeta(BaseModel):
      count: int

  @http_post('/export/', kind=RouteKind.OTHER, response_class=XlsxResponse, file_meta=ExportMeta)
  def action_export(self, data: ExportRequest, **kwargs):
      rows = ...
      return file_answer(
          render_xlsx(rows), 'bookings.xlsx', XlsxResponse.media_type, ExportMeta(count=len(rows))
      )
  ```

  A route that changes the item goes through the checks of an update (see Rules). Every
  operation of a route class has the OpenAPI extension
  `x-bazis: {resource, route_set, action, kind, public}` (`action` is the method name,
  `kind` is collection, create, item, update, delete, relationship, schema or other,
  `public` whether the route is declared `public=True`), plus `access_action` when the
  route declares it; client generators read it instead of parsing `operationId`. Without
  `kind` a route is `other`; an override keeps the `kind`, `public` and `access_action` of
  the route it overrides unless it declares its own. To change them on an inherited route
  without repeating its decorator, declare it again in the subclass with
  `route_declare(route, **facts)` (`bazis.core.routes_abstract.initial`; `kind`, `public`,
  `access_action`, `dependencies`; the path, the function, the callbacks stay):
  `action_transit = route_declare(StatusyRouteSetBase.action_transit, public=True)`.

### Who may call an action: `public`, `access_action`

- Who may call an action (a route of kind `other`): `public=True` opens it to anonymous
  users and limits it by `BAZIS_THROTTLE_PUBLIC` per user or IP address (see Request rate
  limits); `access_action=CrudAccessAction.<X>` (`bazis.core.schemas.enums`, or an
  `AccessAction` of a package such as `StatusyAccessAction`) is the permission it
  requires. The core has no users and only records them: without bazis-permit `public`
  only adds the default throttle and `access_action` does nothing. bazis-permit enforces
  them in `route_check` (the hook of `InitialRouteBase` that runs before the function of a
  route, in its transaction): a public action is open to all; with `access_action` the
  roles decide (also the roles for anonymous users), on the model for an action of the
  collection, on the item (`{item_id}`, taken before the action runs) for an action of an
  item; with neither only authenticated users (`permit.W007` unless `public=False` says
  so). The core `/_id/` route declares `access_action=view`: it is open as `GET /`.

### The errors in the OpenAPI

- The OpenAPI operations document the errors they fail with (`SchemaErrors`): 400 and 422
  on the CRUD operations, 409 on the create and the update (bazis 2.24), 404 on every
  route of an item (`{item_id}` in the path), 403 on the relationships routes. The core has no authentication, so no 401 and no `security` (but for a `public=True` route, see below).
  An id in the path that cannot be a primary key of the model (`not-a-uuid`) is 404, like
  a missing item, on every route of an item (also the custom ones that take the item with
  `set_item`/`get_item`).
  A route class or package that fails its routes with a status adds it by extending the
  classmethod `route_responses(route_ctx)` (call `super()`); `responses=` of a decorator
  wins. Other facts of the operation (`security`, extensions) are added the same way by
  extending `route_openapi_extra(route_ctx)` (`x-bazis` is its base; never change the route
  context there). Document only what the route can really return.
  A `public=True` route has `security: [{}]` in its operation (bazis 2.21): FastAPI extends the
  `security` of the dependencies of the route (an `OAuth2PasswordBearer(auto_error=False)`
  gives `[{OAuth2PasswordBearer: []}]`) by it, the result `[{OAuth2PasswordBearer: []}, {}]`
  means authentication is optional; a route that is not public is unchanged. It only reflects
  the flag `public`: the authentication package must make its dependency of the user agree
  with it, a route with `public=True` and a required user dependency answers 401 anyway
  (override the user for such a route, as bazis-uploadable does).

### Request rate limits (throttle)

`throttle(rate, key='user_or_ip', scope=None)` (`bazis.core.throttle`) is a FastAPI
dependency that limits the requests of a route in a fixed window counted in the default
cache (Redis): over the rate the request fails with 429 `ERR_THROTTLED` and the header
`Retry-After` (seconds to the next window).

```python
from bazis.core.throttle import throttle

class CertificateRouteSet(PermitRouteBase):
    @http_get('/verify/', public=True, dependencies=[throttle('10/minute', key='ip')])
    def action_verify(self, code: str, **kwargs): ...

    @http_post('/export/', access_action=CrudAccessAction.VIEW,
               dependencies=[throttle(lambda: settings.TRAINING_EXPORT_RATE)])
    def action_export(self, **kwargs): ...
```

- `rate`: `'<number>/<second|minute|hour|day>'` (or `s`, `m`, `h`, `d`); a callable
  returning one is read on every request (a dynamic setting of the project, editable in the
  admin; None or `''` means unlimited). An invalid rate fails at import; an invalid rate of
  a callable is logged and does not limit.
- `key`: `user_or_ip` counts the user of the route (`self.inject.user` of bazis-users) when
  he is authenticated, else the IP address; `ip` always the IP address. On a route that is
  not a route class `throttle` counts by the IP address.
- The IP address is `request.client.host`, the address uvicorn gives: Bazis does not read
  `X-Forwarded-For` itself. Behind a reverse proxy, uvicorn (or the gunicorn worker) takes
  the client from `X-Forwarded-For` only for the proxies it trusts: `forwarded_allow_ips`
  of the gunicorn config (the deploy template of the samples reads
  `BS_FORWARDED_ALLOW_IPS`, default loopback and the private networks), `--proxy-headers
  --forwarded-allow-ips` of uvicorn. Never `'*'` on a server clients reach directly: any
  client then picks its address in the header and escapes the limits. If the proxy is not
  trusted (its address missing from the list), every request has the address of the proxy:
  all anonymous users share one count and are throttled together.
- `scope`: routes that name the same scope share the count; by default each route counts
  its own.
- An action declared `public=True` without a throttle of its own gets
  `throttle(BAZIS_THROTTLE_PUBLIC)` (`'30/minute'` per user or IP address, a dynamic
  setting validated in the environment and the admin; `''` turns it off). A throttle the
  action declares replaces it.
- `BAZIS_THROTTLE_ENABLED` (dynamic, true) turns all of them off;
  `BAZIS_THROTTLE_EXEMPT` (an import path of a function `(request, ident) -> bool`,
  `ident` is `user:<pk>` or `ip:<address>`) exempts requests, e.g. by a whitelist of the
  project. The cache failing (Redis down) is logged and lets the requests through.
- Tests: the pytest plugin of bazis-test-utils (2.5.2) resets the counts before each test
  (`bazis.core.throttle.throttle_reset()`), so a test of a throttle counts from zero and the
  other tests never inherit a 429; no fixture of the project clears the cache for it.
- A limit on a business count (attempts per assignment, messages per day of a user) is an
  invariant of the data, not a rate: keep it in `validate_item` (see Invariants of the
  items).

### Code around every route: `BAZIS_MIDDLEWARES`, `<action>__before`/`__after`

- `BS_BAZIS_MIDDLEWARES` (import paths, for every route set) and the attribute
  `bazis_middlewares` of a route set (for its routes, after those of the setting) name
  generator functions `(route, *args, **kwargs)` run around a route: the code before the
  first `yield` runs before the route, the `yield` receives what the route returns (the
  `Response` of an action of `JsonapiRouteBase` with a JSON:API response, else the value
  of the method of the action, e.g. its response model, which FastAPI serializes after the
  middlewares; None when the route raised), and a second value yielded replaces it:

  ```python
  def timing(route, *args, **kwargs):
      start = time.monotonic()
      result = yield
      if isinstance(result, Response):  # starlette.responses
          result.headers['x-elapsed'] = f'{time.monotonic() - start:.3f}'
  ```

- A method `<action>__before(self, *args, **kwargs)` / `<action>__after(...)` of a route set
  (`action_retrieve__before`) runs before / after that action, with its arguments, inside
  its transaction and after `route_check`; an exception refuses the request. A check of
  every action of a package belongs in `route_check`, a write in the hooks of the writes.

## Writes and errors

- Logic around writes: the hooks of the route (below). They are for the side effects of
  the writes of the route; a rule about the item (an invariant) belongs in `validate_item`
  of the model (see Invariants of the items), which no way of writing bypasses.

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
- A to-many relationship is written by one rule, whatever writes it (the create, the
  update, the relationships endpoints: `PATCH` sets, `POST` adds, `DELETE` removes): an
  object a reverse foreign key unlinks is deleted if the foreign key cannot be null, else
  its foreign key is cleared; a many-to-many relationship only unlinks. Deleting the
  object needs the `delete` access of the default route of its model (see
  `restrict_queryset`), otherwise 403 `ERR_RELATION_ACCESS` and nothing is written; a
  route that does not override `restrict_queryset` allows it, a model without a route
  refuses it (403: no route tells the access). An object that other objects refer to
  with `PROTECT` or `RESTRICT` is not deleted: 409 `ERR_CONFLICT` (`meta.types` the types
  of those objects) and nothing of the request is written. `DELETE` of an object that is
  not linked changes nothing (204, as JSON:API requires). A create unlinks nothing, so it
  deletes nothing.
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
  raised anywhere else (a hook, a route, a lookup by a value that cannot be a key such as
  `filter(pk='not-a-uuid')`) answers 422 `ERR_ITEM_INVALID` too: a field of a dict at
  `/data/relationships/<field>` (a relation of the model of the route) or
  `/data/attributes/<field>`, a message without a field at `/data`; on GET (no body) a
  field at its query parameter `/query/<field>` and a message without a field with no
  pointer. It logs a WARNING with its traceback (bazis 2.16; a 500 before): it is a safety net, keep the rules in
  `validate_item` and type the ids of the request schemas as keys. The `ValueError` of a
  lookup by a malformed number or date is still a 500. The routes do not call
  `full_clean()`: `Model.clean()` and the `validators` of the fields do not run on the API.
- From a hook or a custom route: `raise JsonApiBazisException([JsonApiBazisError(message,
  loc=('body', 'data', 'attributes', '<field>'), code='ERR_...')], status=422)`
  (`bazis.core.errors`). The status of the response is the status of the exception (400
  by default); each error keeps its own (422 by default). `loc` is the source of the error:
  starting with `path`, the parameter `/<rest>`; otherwise the pointer, joined with `/`,
  without a leading `body` (`('attributes', f)` is `/attributes/f`, not a pointer into
  the document). `cookies=[JsonApiCookie(key, value, max_age, httponly=..., secure=...,
  samesite=..., path=...)]` sets cookies on the error response (bazis 2.19; a plain
  `(key, value, max_age)` tuple is a cookie with the defaults of Starlette: path `/`,
  SameSite `lax`).
- What the application answers: `JsonApiBazisException` with its status and errors; the
  errors of the request schemas 422 `ERR_VALIDATE` (the title is the Pydantic error type,
  the detail its English message); an `item_id` that cannot be a key 404; a
  `JsonApiHttpException` (`JsonApi403Exception` is `ERR_FORBIDDEN`) its status, `code`
  and `detail`; another `HTTPException` (an unknown path 404, a wrong method 405) its
  status and `detail`, with `ERR_REQUEST` when a route raised it; a query error 400
  `ERR_FILTER` (of the aggregates `ERR_AGGREGATE`); an `IntegrityError` of a unique or an exclusion constraint (also at the
  commit) 409 `ERR_CONFLICT` ("The change conflicts with the current data";
  `meta.constraint` names the constraint with DEBUG; the transaction of the request is
  rolled back); on the create and the update of a route, a unique constraint of its model
  (`Meta.constraints`, also of expressions, `unique=True`, `unique_together`) whose fields
  the user all writes (in the schema of the write he has, not read-only) an error for each
  of its fields at `/data/relationships/<f>` or `/data/attributes/<f>` with the message of
  Django ("... with this ... already exists." or its `violation_error_message`), so a
  parallel duplicate shows at its field as a sequential one does (422 of
  `validate_item`); any other (a field hidden from the user or filled by the server, a
  constraint of another table such as a child an action creates, an action, the
  relationships endpoints, an exclusion constraint) the single error, without a pointer
  and without a name of a field (`JsonapiRouteBase.unique_conflict`), anywhere in the
  request (bazis 2.16; a create answered 409 `ERR_REQUEST` "Data conflict" for any
  integrity error before); a throttled request 429 `ERR_THROTTLED` with `Retry-After`; a body
  larger than `BAZIS_API_MAX_BODY_SIZE` 413 `ERR_BODY_TOO_LARGE`; any
  other exception 500 (the traceback in `detail` only with DEBUG), also another
  `IntegrityError` (a not-null or check constraint: keep such rules in `validate_item`,
  422; a foreign key to a missing object that a route links is 422 `ERR_VALIDATE`, see
  `relations_access_check`, but one a hook or an action writes fails at the commit).
- A request PostgreSQL aborts for a parallel one, a deadlock (SQLSTATE 40P01) or a
  serialization failure (40001), answers 409 `ERR_CONFLICT` "The request conflicted with a
  parallel one: retry it" with `meta.retry: true` (`meta.sqlstate` with DEBUG; bazis 2.16,
  a 500 before). Its transaction is rolled back and the same request may succeed when the
  client sends it again; the core does not repeat it (the request may have done what a
  rollback does not undo: a mail, a task, a count of a throttle). Avoid the deadlock
  itself with one order of the locks (`lock_on_write`, see Invariants under concurrent
  requests). Any other `OperationalError` is a 500.
- A deletion refused by the objects that refer to the deleted ones with `PROTECT` or
  `RESTRICT` (an object a relationship unlinks and deletes, a deletion in a hook) answers
  409 `ERR_CONFLICT` "The objects to delete are referred to by other objects" with
  `meta.types` (their resource types) and rolls the request back (bazis 2.16, a 500
  before). `DELETE` of an item keeps its own errors of `PROTECT` (`MODEL_PROTECTED_RELATION`).
- The pointers (`source`) of the errors of the core, by code. Create and update point into
  the request document; an included item is `/included/<i>` instead of `/data`, `<i>` its
  index in the `included` of the document. The relationships endpoints point into their
  body, the `data` of the relationship.
  - `ERR_VALIDATE`: `/data/attributes/<f>`, `/data/relationships/<f>/...`, `/data/id`, `/data`
    (`missing` for a document without `data`); a related id that cannot be a key of the
    related model, or the id of an object that does not exist of a model whose route does
    not restrict its objects (bazis 2.16), at its identifier,
    `/data/relationships/<f>/data/id`, `/data/relationships/<f>/data/<j>/id`; `source.id` and
    `source.type` name the item when the document gives its id. On the relationships
    endpoints `/data`, `/data/<j>/id` (`/data/id`).
  - `ERR_ITEM_INVALID`: `/data/attributes/<f>`, `/data/relationships/<f>`, `/data`. On the
    relationships endpoints the parameter `/related_field_name`; a Django `ValidationError`
    of a GET route `/query/<f>`.
  - `ERR_CONFLICT` (409) of a unique constraint of the model of a create or an update
    whose fields the user writes: `/data/attributes/<f>`, `/data/relationships/<f>`, an
    error for each field; none otherwise (also on the relationships endpoints).
  - `ERR_RESOURCE_MISMATCH` (409, bazis 2.24) of a create or an update document that is
    not the resource of the route (see API conventions): `/data/type`, `/data/id`, both
    errors in one response when both differ.
  - `ERR_INCLUDE` (400): `/query/include`. `ERR_FILTER` (400): `/query/filter`,
    `/query/sort`, `/query/search`. `ERR_AGGREGATE` (400): `/query/aggregate`,
    `/query/group`.
  - `ERR_RELATION_ACCESS` (403), `ERR_RELATION_LINK` (422): `/data/relationships/<f>`. On
    the relationships endpoints `/data/<j>`, the refused identifier of a to-many
    relationship, else `/data` (a to-one relationship, or an object the change unlinks).
  Up to 2.10 `ERR_VALIDATE` pointed to `/attributes/<f>` and `/relationships/<f>`, also for
  an included item, and the relationships endpoints into the document of an update: a
  client that also serves older servers reads both forms.
- A relation by a foreign key with `to_field` (bazis 2.19): its identifiers are primary keys
  of the related objects, as of every relationship (`relationships.<f>.data.id` equals
  `included[].id` and the id of `/<prefix>/<id>/`); the foreign key stores the value of the
  `to_field`. The core translates: a read gives the primary key (`RelationInfo.related_pk`,
  annotated by the queryset of the route), a write stores the value of the object found by
  its primary key (`RelationInfo.fk_value`; no object: 422, never the identifier stored as
  a value of the `to_field`), the filter, sorting and `group` by the relation
  work with primary keys. The checks of the targets are by the primary key. Up to 2.18 the
  identifiers were values of the `to_field`, and the checks looked up by the primary key.
- The titles and the fixed details of the errors of the core follow the language of the
  request (`ru` is translated), also the diagnostics of `ERR_FILTER` and `ERR_INCLUDE` (the
  names in them as given); the Pydantic messages (`ERR_VALIDATE`) and the messages of
  Django and Python in `ERR_FILTER` (a value that is not a number) are English.

## API conventions

- The `data` of a create or an update document is the resource of the route (bazis 2.24):
  its `type` may be left out (on a create and on an update, whatever the route shows), a
  `type` given is exactly the type of the route (on a create a model that inherits the
  model of the route has its own type and route) or, on an update, the type the route
  shows the item with (a route whose queryset gives the instances of a child model takes
  both), and the `id` of an update (required, 422 `ERR_VALIDATE` without it) is the id of the path, compared as a
  key of the model (a UUID in any case). Anything else is 409 `ERR_RESOURCE_MISMATCH` at
  `/data/type` and (or) `/data/id`, before anything is written; the `id` of a create is
  the id of the client. The model of a write is the model of the schema of the route,
  never the text of the request; an `included` item is validated by the schema of its
  type. Up to 2.23 the `type` was not checked (a create built the model it named) and the
  `id` of an update was ignored.
- `filter` is one expression: `filter=status=new&price__gte=20`, `filter=(a=1|b=2)`,
  `~a=1` (not), nested fields `filter=customer__name=Acme` (an `EXISTS` subquery),
  `customer__exists=true|false` (`customer__isnull` is the opposite), full-text
  `$search=text` (the search fields of the route) or `customer__$search=text` (the search
  fields of the default route of the customers), `crm.customer=<id>,<id>` (the objects
  related to those customers); `search=text` searches the search fields of the route
  (`search_fields`; a route that does not declare them searches the text fields it shows
  the user, see below; `search_fields = []` turns the search off):
  the text is split into words (spaces and commas), and an object matches when each word
  is in one of its search fields (`search=Ann Smith` with the search fields `first_name`
  and `last_name` finds Ann Smith). A field of the model matches a substring in any case,
  or as the prefix of the field in `search_fields` says (`^name` starts with, `=name`
  exact, `@name` full-text, `$name` regex); a field through a relation (`tag__name`)
  matches only the whole value, as written.
- The filter, `sort` and `search` reach only what the route shows the user: a key of the
  filter and of `sort` starts with a field of the LIST schema of the route (its `fields`;
  `filterLabel`/`orderLabel` of the schema) or `id` (`pk`); the search reaches the fields
  the user reads in the objects of the list or on their cards, of the LIST or the RETRIEVE
  schema (bazis 2.23; of LIST alone when the route does not serve RETRIEVE, without
  `action_retrieve`: the RETRIEVE schema of the responses of a create or an update does
  not count). A
  relation of it leads into the objects the default route of the related model shows (its
  `restrict_queryset` for `view` with the user of the route), where the key goes on with
  the fields of that route, the same way (a model without a route: only `id`/`pk`,
  `exists`, `isnull`). A field only the card shows is searched but is 400 in `filter` and
  `sort`. `sort` goes through to-one relations only (an invisible object sorts
  as null; a relation itself sorts by the key of the related object); the search uses only
  the `search_fields` of the route that are fields it shows (`bazis.W007` warns
  about the others). A route that does not declare `search_fields` (None) searches the
  text fields it shows the user: of its LIST schema in its order, then those only its
  RETRIEVE schema has, in that order (`default_search_fields`): a
  `CharField` or `TextField` of the model (also `SlugField`, `EmailField`, `URLField`)
  without choices and a `TranslatedField` of one (in the language of the request); not
  the relations, the calculated fields, the fields with choices, the numbers, the UUID,
  file, JSON and array fields. A route with `search_fields = []`, or without such fields
  for the user, has no search. `route_search_fields(route_cls)` of
  `bazis.core.utils.query_complex` lists the fields searched (declared or by default, of
  the LIST and RETRIEVE schemas of the registered class; bazis-permit narrows them per
  user). The search assumes that the card shows every object of the list (the core and
  bazis-permit restrict both with one `restrict_queryset` for `view`): a route whose item
  shows fewer objects than its list (its own `get_queryset_for_item`) shows on the card
  only the fields that may be searched in every object of the list: declare
  `search_fields` of LIST fields, or make the list a route without `action_retrieve`. A
  search by substring (`icontains`) uses no btree index: for a large list declare
  `search_fields` (or `[]`), and a `pg_trgm` index if needed. Anything else is 400
  `ERR_FILTER` (pointer `/query/filter`, `/query/sort` or `/query/search`), the same
  answer as for a field that does not exist: to filter or sort by a field, show it in the
  LIST schema of the route, to search by it, in the LIST or the RETRIEVE schema.
  `filters_aliases` of the route are not checked (the
  relations they lead to are). `QueryToOrm`/`SearchToOrm` without `scope` (permission
  conditions, `filter:` restrictions) and the services with `scope=None` are not
  restricted. A package that changes the schemas per user overrides the classmethod
  `query_fields(user=None, *, api_action=CrudApiAction.LIST, **kwargs)` of the route: the
  fields of the schema of `api_action` (LIST or RETRIEVE) for the user, the schema factory
  from `query_schema_factory(api_action)`. An override written before bazis 2.23 (without
  `api_action`, which it takes in `**kwargs`) gives its LIST fields for RETRIEVE too: the
  search stays within the LIST schema, as before.
  Only for the compatibility with released clients that send a key the route has no field
  for (bazis 2.20): `filter_keys_ignored = frozenset({'dt_deleted'})` of the route leaves
  out every key of the `filter` of its requests that starts with such a name, whatever
  its lookup, value and `~` (in an `or` it is left out too, not true). Not after a
  relation (`capsule__dt_deleted` on another route stays 400), not another route of the
  model, not the conditions of the code (`QueryToOrm` without a scope: the permissions,
  `filter:` restrictions). Not a filter key of the route: a field of its LIST schema,
  `id`/`pk` or a filters alias (`bazis.E002`); it is not in `route_filter_fields/`. A new
  client must not send it, and a missing field is never made a filter this way.
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
  is not `as_filter` are an error 400 `ERR_FILTER` (a `filter:` restriction or a condition
  of a permission with one fails every request it applies to).
  `iexact`/`istartswith`/`iregex`/`search`/`$search` apply to every word of the value. URL-encode the value of `filter`;
  the server decodes the expression once more and every value once more, so a value with
  `&|()[]~=+%` is percent-encoded twice inside the expression; quotes are removed from
  values.
- `sort=-dt_created,number,customer__name`, `sort=location__distance(37.62,55.75)` (see
  Points and distances), `page[limit]` / `page[offset]`
  (`BAZIS_API_PAGINATION_PAGE_SIZE_MAX` caps the limit), `include=customer,items`,
  `fields[crm.order]=number,customer` (sparse fieldsets).
- Aggregates of a list (bazis 2.17; a total, a chart): `meta=aggregates` with
  `aggregate=count,sum(amount),avg(amount),min(due),max(due),count(customer)` (comma
  separated; `count` the objects, `count(f)` those with a value of `f`; without
  `aggregate` only `count`) and optionally `group=<field>` or `group=<date field>:day`,
  `:week` (from Monday), `:month`. They count every object of the list with its `filter`
  and `search` (the objects of `get_queryset_for_list`, so the ones bazis-permit lets the
  user view; each once, by its key through the base manager of the model, also when a
  join of the list repeats it or the default manager hides it), not its
  page, sorting or sparse fieldsets, in one query; without
  `meta=aggregates` the parameters are not read. `meta.aggregates` is
  `{"count": 4, "sum(amount)": "60.50"}` (the key is the term as written), with `group` a
  list ordered by the value, the objects without one last:
  `[{"group": "2026-01-01", "values": {"count": 2, "sum(amount)": "30.50"}}, {"group": null, ...}]`.
  A group is a string: the choice, `true`/`false`, the id of a to-one relation (as its
  `relationships` data shows it), the ISO date of the start of the bucket (in the time zone
  of the project, `TIME_ZONE`); at most `BAZIS_API_AGGREGATE_GROUPS_MAX` groups (1000,
  `BS_BAZIS_API_AGGREGATE_GROUPS_MAX`; more is 400 `ERR_AGGREGATE` at `/query/group`:
  narrow the list with a filter, or group a date by week or month); a decimal is a string, a date or a time ISO 8601, an average of an
  integer field a float; over no object `count` is 0, the others `null`, the groups `[]`.
  A field is a column of the model the `filter` of the route reaches for the user (the
  LIST schema, `query_fields`; not a calculated field, a to-many relation or a path
  `a__b`): `sum`/`avg` take a number, `min`/`max` a number or a date, `count` any; `group`
  takes a field with `choices`, a boolean, a foreign key or one-to-one, or a date with a
  bucket. Anything else is 400 `ERR_AGGREGATE` (pointer `/query/aggregate` or
  `/query/group`), a hidden field answered as one that does not exist. Every
  `JsonapiRouteBase` has it; an aggregate over other objects or of a calculated field is a
  route of its own (Routes: a report).
- `include` (retrieve, create, update) names relations of the schema of the action (an
  update also those of the create schema); a relation that is not in it (a reverse
  relation not added to `fields`, an attribute, a path `a.b`) is 400 `ERR_INCLUDE` with the
  pointer `/query/include`. A relation in the schema that a package hides from the user (the field
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
on a write, in both directions longitude, latitude of WGS 84 (RFC 7946), whatever the SRID
of the field (a field of another SRID stores it transformed and shows it transformed
back), so the value of a GET can be sent back. A write is of the type of the field (a
point for a `PointField`), of its dimension (no third coordinate on a 2D field), finite
and in range (-180..180, -90..90), without a `crs` member; anything else is 422
`ERR_VALIDATE` at the attribute. On a route whose LIST schema has `location`:

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

## E-mail

The core configures the mail of Django: `MAILERS['default']` (Django 6.1) uses
`BAZIS_EMAIL_BACKEND` (default `bazis.core.mail.DynamicSMTPEmailBackend`), an SMTP backend
that reads the dynamic settings `BAZIS_EMAIL_HOST`, `BAZIS_EMAIL_PORT`,
`BAZIS_EMAIL_HOST_USER`, `BAZIS_EMAIL_HOST_PASSWORD`, `BAZIS_EMAIL_USE_TLS`,
`BAZIS_EMAIL_USE_SSL`, `BAZIS_EMAIL_TIMEOUT` (seconds, default 10, 0 - unlimited)
(editable in the admin, `BS_BAZIS_EMAIL_*` as their defaults) every time it opens a
connection; `DEFAULT_FROM_EMAIL` is the sender (dynamic too, `BS_DEFAULT_FROM_EMAIL`,
default `webmaster@localhost` as in Django: set it to an address of the domain). A value
set in the admin wins over the variable (see Settings: `BS_*`); `bazis_doctor` warns of an
empty sender, with which every mail fails (`bazis.W009`, a value saved by bazis before
2.16; the mails fail with `Invalid address`): set it in the admin or with `manage.py
constance set DEFAULT_FROM_EMAIL noreply@<domain>`. Send with Django:

```python
from django.core.mail import send_mail

send_mail(_('Your certificate'), text, None, [user.email])   # None: DEFAULT_FROM_EMAIL
```

- `BS_BAZIS_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` prints the mails
  (development); tests get the `locmem` backend of Django (`django.core.mail.outbox`).
- `send_mail` is synchronous: do not send many mails in a request; send them from a
  background task (bazis-bg) after the commit (`transaction.on_commit`), and let a failure
  of one address not stop the others (catch `OSError`, which covers
  `smtplib.SMTPException` and the connection errors, and log it), not a bare
  `except Exception`. An unresponsive server holds the sender up to `BAZIS_EMAIL_TIMEOUT`
  for the connection and each command, then fails (`TimeoutError`, or
  `smtplib.SMTPServerDisconnected` once connected).
- Options set explicitly in `MAILERS['default']` override the dynamic settings.

## Rules


- Every way of changing an object goes through the checks of an update: do not change
  relations in custom endpoints without the route (use `relationships_change`, which
  applies the update schema, the visibility of the targets, the `filter:` restrictions
  and the hooks).
- Keep an invariant of an item (no overlap, a limit, a consistency of fields) in
  `validate_item` of the model, not in the hooks of a route: the hooks of create and
  update do not run for the relationships endpoints, the transits, the admin or `save()`.
  An invariant over several rows declares their parent in `lock_on_write` (every write
  locks it first, in every path) and has a database constraint as the barrier (see
  Invariants of the items).
- An action open to anonymous users (`public=True`) is limited (the default
  `BAZIS_THROTTLE_PUBLIC`, or its own `throttle`): never leave a guessable code or a costly
  operation open without a rate limit.
- Restrict the objects of a model that a user must not see in `restrict_queryset` of its
  default route, not only in `get_queryset`: `get_queryset` restricts the route's own
  list and item, the relationships, `included` and the filters through a relation of the
  other routes use `restrict_queryset`.
- A route that hides fields of its model (a projection with `fields`) hides them from the
  filter and the sorting (out of the LIST schema) and from the search (out of the LIST and
  the RETRIEVE schemas: a field the card shows is searched); do not list hidden fields in
  `search_fields`. Without `search_fields` a route searches every text field it shows (LIST
  and RETRIEVE): declare them to search fewer fields, `search_fields = []` for a route
  without a search. A route whose own `get_queryset_for_item` shows fewer objects than its
  list declares `search_fields` of LIST fields, or makes the list a route without
  `action_retrieve`.
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
