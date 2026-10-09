# Bazis for tools and AI agents

Each Bazis package describes itself, so that tools and AI agents can choose the packages a
project needs, use them the way they are meant to be used and check the result.

## In a project

- `python manage.py bazis_introspect [packages|settings|models|routes]` prints the facts
  about the project as JSON: the installed Bazis packages with their manifests, the
  settings (secrets hidden, dynamic settings without a value), the JSON:API models with
  their relations, and the route classes with their base classes and routes (path,
  methods, `action`, `kind`).
- `python manage.py bazis_doctor [--deploy] [--database ALIAS] [--json]` runs the Django
  system checks, including the checks of the Bazis packages that need the routes, and exits
  with an error if any check fails with an error. `--deploy` adds the deployment checks.
  The database checks (Django tag `database`: they compare the project with the data of
  its database) run against the database `default` when it can be reached and are skipped
  with the info `bazis.database` when it cannot (PostgreSQL is probed with a connect
  timeout of 5 seconds; `SILENCED_SYSTEM_CHECKS` silences the info); `--database`
  (repeatable) names the databases, and one that cannot be reached is an error
  (`bazis.database`).
- `bazis.core.introspect` is the Python API of the same data.
- The OpenAPI schema (`/api/openapi.json`) carries the same facts about each operation of a
  route class in the extension `x-bazis` (`resource`, `route_set`, `action`, `kind`; see
  the OpenAPI docs), for client generators; other operations have none. The operations
  also document the JSON:API errors they fail with (404 of the item routes, 403 of the
  relationships routes; a package that adds authentication adds the 401 of its routes).
- [bazis-mcp](https://github.com/ecofuture-tech/bazis-mcp) serves the same data and the
  catalog of all Bazis packages to MCP clients (Claude Code, IDEs).

## In a package

A package `bazis-<name>` ships two files in its module (`bazis/contrib/<name>/`):

- `AGENTS.md` — how to use the package: setup, the classes to extend, the rules. Short and
  exact; it is read by agents, not people browsing the docs.
- `bazis_manifest.toml`:

  ```toml
  [package]
  name = "bazis-permit"                     # the distribution name
  summary = "..."
  solves = ["...", "..."]                   # the tasks the package is for
  requires = ["bazis", "bazis-users"]       # Bazis packages it needs
  pairs_well = ["bazis-author"]             # packages often used with it

  [[extension_points]]                      # the classes and functions to use
  name = "PermitRouteBase"
  import = "bazis.contrib.permit.routes_abstract.PermitRouteBase"
  use_when = "..."

  [[pitfalls]]                              # mistakes to avoid
  text = "..."
  check = "permit.W001"                     # optional: the system check that detects it
  ```

Mistakes that can be detected are Django system checks of the package (ids
`<package>.E/W<nnn>`, registered in `AppConfig.ready`) and listed as pitfalls with their
`check` id. A check that needs the routes uses `bazis.core.introspect.loaded_app()` and
returns no messages when the application is not loaded.

Every package tests its manifest, so that it cannot drift from the code:

```python
from bazis.core.introspect import validate_manifest

def test_manifest_is_valid():
    assert validate_manifest('bazis.contrib.permit') == []
```

`validate_manifest` checks that every `import` path imports and every `check` id is
defined in the package.
