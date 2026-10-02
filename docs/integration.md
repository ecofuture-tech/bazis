# Integration of the Bazis packages

The framework is split into packages in separate repositories, and the CI of each package
installs its Bazis dependencies from PyPI: a change of the core that breaks a package would
only be seen after the core is released.

The **Integration** workflow (`.github/workflows/integration.yml`) runs, for every package,
its migrations check, `manage.py bazis_doctor` and its tests, with the Bazis packages it
depends on (also through the others) installed from their repositories by
`scripts/integration_install.sh`. The checkouts override the requirements on them, so a
change can raise the minimal version of a Bazis package to the one it is about to release:

- on every pull request of the core: the core of the pull request, the other packages at
  the branch of the same name if their repository has it and it is based on the current
  `main` (a merged branch left behind is ignored), otherwise at `main`;
- nightly, at `main`;
- on demand (**Run workflow**, input `ref`): for a change that spans several repositories,
  push the same branch to all of them and run the workflow at that branch before merging
  any of them.

Locally (PostgreSQL with PostGIS and Redis; Kafka for the async packages; the variables of
the Tests workflow of the package):

```bash
uv venv /tmp/integ && export VIRTUAL_ENV=/tmp/integ
SRC=/tmp/integ-src CORE_DIR=$PWD scripts/integration_install.sh bazis-permit
cd /tmp/integ-src/bazis-permit/sample
/tmp/integ/bin/python manage.py bazis_doctor
/tmp/integ/bin/python -m pytest ../tests -o addopts="" -p no:cacheprovider
```

When a package is added to the framework, add it to the matrix of the workflow (with
`kafka: true` and its topic if its tests need a Kafka consumer).
