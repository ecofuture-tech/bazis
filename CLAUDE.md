# Bazis

JSON:API framework on Django + FastAPI + Pydantic. The framework code is in `bazis/core`,
the sample project used by the tests is in `sample/`, the tests are in `tests/`.

## Running the tests

The tests need PostgreSQL with PostGIS and Redis (see `.github/workflows/tests.yml`).
Run them from the `sample` directory:

```bash
cd sample
BS_DEBUG=true \
BS_SECRET_KEY=local-secret-key-that-is-long-enough-0123456789 \
BS_DATABASES__DEFAULT__HOST=localhost BS_DATABASES__DEFAULT__PORT=5432 \
BS_DATABASES__DEFAULT__NAME=bazis BS_DATABASES__DEFAULT__USER=postgres \
BS_DATABASES__DEFAULT__PASSWORD=postgres \
BS_CACHES__DEFAULT__LOCATION=redis://localhost:6379/1 \
python -m pytest ../tests -o addopts="" -p no:cacheprovider
```

Lint: `ruff check bazis tests sample`.

Test expectations must not depend on the database collation (CI uses `en_US.utf8`),
and SQL assertions go through `tests/utils/assert_sql.py`, which normalizes the SQL.

## Authorship

Every commit, tag and pull request of the Bazis repositories is authored by the maintainer,
Ilya Kharyn <ilya.tt07@gmail.com>. AI assistants never appear as an author, committer or
co-author: no `Co-Authored-By` or session trailers in commit messages, no "Generated with"
lines in pull requests. Set `git config user.name "Ilya Kharyn"` and
`git config user.email "ilya.tt07@gmail.com"` in every clone before committing, and check
`git log -1 --format='%an <%ae>'` before pushing.

## Releasing

A release is the tag `vX.Y.Z` on `main`: the Build and Publish workflow builds the package
(the version comes from the tag through setuptools-scm) and publishes it to PyPI
(pre-releases `-alphaN`/`-betaN`/`-rcN` go to Test PyPI) and creates the GitHub release.

Claude Code sessions cannot push tags. Release through the **Release** workflow instead:

1. Make sure the changes are merged into `main` and the Tests workflow is green on the
   `main` head commit (the Release workflow checks this and refuses otherwise).
2. Add the release notes as `docs/releases/X.Y.Z.md` in the change being released.
3. Start the workflow `release.yml` on `ref: main` with the input `version: X.Y.Z`
   (GitHub API: `POST /repos/ecofuture-tech/bazis/actions/workflows/release.yml/dispatches`;
   with the GitHub MCP tools: `actions_run_trigger`, method `run_workflow`).
4. The Release run creates the annotated tag and starts Build and Publish on it. Check
   that both runs succeed and that the version appears on https://pypi.org/project/bazis/.

Pick the version by semver: breaking changes (settings renamed or required, dependency
removed, behavior changed) bump the minor version while the project is below 3.0.

## The Bazis packages

The framework is split into packages in separate repositories of `ecofuture-tech`, each with
its own `CLAUDE.md`, Tests and Release workflows. Release them in dependency order (CI of a
package installs its Bazis dependencies from PyPI):

1. `bazis` → `bazis-test-utils`
2. `bazis-users`, `bazis-ws`, `bazis-bulk`, `bazis-uploadable`
3. `bazis-author`, `bazis-authing` (users) → `bazis-permit` (users, author for its tests)
4. `bazis-statusy` (permit), `bazis-bg` (author)
5. `bazis-async-background` (ws, Kafka) → `bazis-async-request`
6. `bazis-mcp` (its catalog describes the latest releases of the others)

The Integration workflow runs the tests of every package against the code of the core and
of the packages it depends on (see `docs/integration.md`); it runs on every pull request of
the core.

A package requires the versions of Bazis and of the sibling packages whose API or behavior it
relies on (for example a security fix it builds on); new releases of the other packages do
not raise the floors.

Each package ships `AGENTS.md` and `bazis_manifest.toml` in its module for tools and AI
agents (format: `docs/agents.md`); keep them exact when the package changes, its
`test_manifest.py` verifies the imports and check ids. `manage.py bazis_introspect` and
`manage.py bazis_doctor` show the facts and the problems of a project.

Security boundaries that span packages:

- Every way of changing an object must go through the checks of an update: the
  relationships endpoints (`JsonapiRouteBase.relationships_change`) accept only the
  relations of the update schema and call `hook_before/after_relationships_change`, which
  bazis-permit uses.
- An invariant of an item lives in `JsonApiMixin.validate_item`, which the core calls once
  per write whatever writes it (the routes, `save()`, the many-to-many managers); a package
  that writes an item in several steps (the transits of bazis-statusy) declares them with
  `defer_validate_item(item, source=...)` so that the item is validated once.
- A relationship links only the objects the default route of the related model shows
  (`restrict_queryset`), and `included` shows only those objects
  (`JsonapiRouteBase.relations_access_check`, `JsonApiMixin.fields_for_included`): a
  package restricts the objects of its models there, not only in `get_queryset`.
- Session JWTs (bazis-users) require `exp` and `sub`; on HTTP a token without `exp` (the
  store token of bazis-authing) is anonymous, bazis-ws rejects it.
- Anonymous WebSocket channels (bazis-ws) live under `user_ws:anon:`; bazis-async-background
  resolves channels with the same functions.
