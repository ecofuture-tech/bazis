# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
What the core builds must not depend on the hash seed of the process (the iteration order of
the sets of strings): the translated titles and the schema names end up in the OpenAPI, which
is hashed to detect a stale frontend contract.
"""

import array
import json
import os
import struct
import subprocess
import sys

import pytest


SEEDS = ('0', '1', '2', '3', '4', '5')


def run_processes(runs: dict[str, tuple[str, str, dict]]) -> dict[str, str]:
    """
    Runs `{key: (code, hash seed, environment)}` in parallel subprocesses with the settings
    of the sample, and returns the last line each one printed.
    """
    processes = {
        key: subprocess.Popen(
            [sys.executable, '-c', code],
            env={
                **os.environ,
                'DJANGO_SETTINGS_MODULE': 'sample.settings',
                'PYTHONHASHSEED': seed,
                **env,
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for key, (code, seed, env) in runs.items()
    }
    outputs = {}
    for key, process in processes.items():
        stdout, stderr = process.communicate(timeout=300)
        assert process.returncode == 0, stderr
        outputs[key] = stdout.splitlines()[-1]
    return outputs


def write_mo(path, messages: dict[str, str]) -> None:
    """
    Writes a compiled gettext catalog (the format of `msgfmt`, which CI may not have).
    """
    messages = {'': 'Content-Type: text/plain; charset=UTF-8\n', **messages}
    keys = sorted(messages)
    ids = strs = b''
    offsets = []
    for key in keys:
        key_bytes, value_bytes = key.encode(), messages[key].encode()
        offsets.append((len(ids), len(key_bytes), len(strs), len(value_bytes)))
        ids += key_bytes + b'\0'
        strs += value_bytes + b'\0'
    keys_start = 7 * 4 + 16 * len(keys)
    values_start = keys_start + len(ids)
    key_offsets, value_offsets = [], []
    for id_offset, id_len, str_offset, str_len in offsets:
        key_offsets += [id_len, id_offset + keys_start]
        value_offsets += [str_len, str_offset + values_start]
    path.parent.mkdir(parents=True)
    path.write_bytes(
        struct.pack('Iiiiiii', 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
        + array.array('i', key_offsets + value_offsets).tobytes()
        + ids
        + strs
    )


TRANSLATE_NAME = (
    'import django; django.setup(); '
    'from django.conf import settings; '
    'from django.utils import translation; '
    "translation.activate('ru'); "
    "print(translation.gettext('Name'), settings.LOCALE_PATHS)"
)


@pytest.fixture
def packages_translating_the_same_msgid(tmp_path):
    """
    Packages that translate "Name" differently into Russian (as bazis-permit, bazis-statusy
    and bazis-uploadable do), each into its own name: three Bazis packages (portions of the
    namespace `bazis.contrib`), an app of the project and a library that is not an app.
    Returns the environment that makes them importable.
    """
    packages = [
        tmp_path / 'bazis' / 'contrib' / name for name in ('fake_first', 'fake_second', 'fake_unused')
    ] + [
        tmp_path / 'fake_project',
        tmp_path / 'fake_library',
        tmp_path / 'fake_config_init',
        tmp_path / 'fake_config_package' / 'apps',
    ]
    for root in packages:
        write_mo(root / 'locale' / 'ru' / 'LC_MESSAGES' / 'django.mo', {'Name': root.name})
        (root / '__init__.py').write_text('')
    # apps whose AppConfig is declared in the package itself and in a subpackage `apps`
    config = 'from django.apps import AppConfig\n\nclass {cls}(AppConfig):\n    name = {name!r}\n'
    (tmp_path / 'fake_config_init' / '__init__.py').write_text(
        config.format(cls='FakeConfig', name='fake_config_init')
    )
    (tmp_path / 'fake_config_package' / '__init__.py').write_text('')
    (tmp_path / 'fake_config_package' / 'apps' / '__init__.py').write_text(
        config.format(cls='FakeConfig', name='fake_config_package.apps')
    )
    return {'PYTHONPATH': os.pathsep.join([str(tmp_path), os.environ.get('PYTHONPATH', '')])}


def test_translations_follow_installed_apps_in_every_process(
    packages_translating_the_same_msgid,
):
    """
    Like Django orders the catalogs of the apps, the first installed app wins, whatever the
    hash seed; a package that is not installed never wins over an installed one.
    """
    env = {
        **packages_translating_the_same_msgid,
        'BS_INSTALLED_APPS': json.dumps(['bazis.contrib.fake_second', 'bazis.contrib.fake_first']),
    }

    outputs = run_processes({seed: (TRANSLATE_NAME, seed, env) for seed in SEEDS})

    assert {seed: output.split()[0] for seed, output in outputs.items()} == {
        seed: 'fake_second' for seed in SEEDS
    }
    assert len(set(outputs.values())) == 1


def test_project_app_wins_over_packages_that_are_not_installed(
    packages_translating_the_same_msgid,
):
    """
    An app of the project (not a Bazis package, not imported when the settings are built)
    wins over a Bazis package that is not installed, and the catalogs do not depend on the
    modules the process imported before the settings (manage.py, uvicorn and pytest import
    different ones).
    """
    env = {**packages_translating_the_same_msgid, 'BS_INSTALLED_APPS': '["fake_project"]'}
    preloaded = 'import bazis.contrib.fake_unused, fake_library; ' + TRANSLATE_NAME

    outputs = run_processes(
        {'plain': (TRANSLATE_NAME, '0', env), 'preloaded': (preloaded, '0', env)}
    )

    assert outputs['plain'].split()[0] == 'fake_project'
    assert outputs['preloaded'] == outputs['plain']
    assert 'fake_library' not in outputs['plain']
    # the catalog of the Bazis package that is not installed is still loaded, under the app
    assert outputs['plain'].index('fake_project') < outputs['plain'].index('fake_unused')


@pytest.mark.parametrize(
    'app, expected',
    [
        ('fake_config_init.FakeConfig', 'fake_config_init'),
        ('fake_config_package.apps.FakeConfig', 'apps'),
    ],
)
def test_app_config_paths(packages_translating_the_same_msgid, app, expected):
    """
    An entry of INSTALLED_APPS that is the path of an AppConfig declared in a package (not
    in a module `apps.py`) gives the catalog of that package.
    """
    env = {**packages_translating_the_same_msgid, 'BS_INSTALLED_APPS': json.dumps([app])}

    output = run_processes({'app': (TRANSLATE_NAME, '0', env)})['app']

    assert output.split()[0] == expected


def test_restrict_filters_do_not_depend_on_the_process():
    """
    The `filter:` restrictions of a field (bazis-permit) are a set; their order is part of
    the identity of the field and so of the name of the schema.
    """
    code = (
        'import django; django.setup(); '
        'from entity.routes import ParentEntityRouteSet; '
        'from bazis.core.schemas.enums import CrudApiAction; '
        'factory = ParentEntityRouteSet.build_schema_factory(CrudApiAction.RETRIEVE); '
        "fields = factory.fields_patch({'name': {f'filter:name={c}' for c in 'abcdefgh'}}); "
        "print(','.join(next(f for f in fields if f.source == 'name').restrict_filters))"
    )
    expected = ','.join(f'name={c}' for c in 'abcdefgh')

    outputs = run_processes({seed: (code, seed, {}) for seed in SEEDS})

    assert outputs == {seed: expected for seed in SEEDS}
