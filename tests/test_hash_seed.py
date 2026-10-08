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


def run_with_seed(code: str, seed: str, **env) -> str:
    result = subprocess.run(
        [sys.executable, '-c', code],
        env={
            **os.environ,
            'DJANGO_SETTINGS_MODULE': 'sample.settings',
            'PYTHONHASHSEED': seed,
            **env,
        },
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()[-1]


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


@pytest.fixture
def packages_translating_the_same_msgid(tmp_path):
    """
    Three Bazis packages (portions of the namespace `bazis.contrib`) translate "Name"
    differently into Russian, as bazis-permit, bazis-statusy and bazis-uploadable do.
    """
    for package in ('fake_first', 'fake_second', 'fake_unused'):
        root = tmp_path / 'bazis' / 'contrib' / package
        write_mo(root / 'locale' / 'ru' / 'LC_MESSAGES' / 'django.mo', {'Name': package})
        (root / '__init__.py').write_text('')
    return str(tmp_path)


def test_translations_follow_installed_apps_in_every_process(
    packages_translating_the_same_msgid,
):
    """
    Like Django orders the catalogs of the apps, the first installed app wins, whatever the
    hash seed; a package that is not installed never wins over an installed one.
    """
    code = (
        'import django; django.setup(); '
        'from django.utils import translation; '
        "translation.activate('ru'); "
        "print(translation.gettext('Name'))"
    )
    env = {
        'PYTHONPATH': os.pathsep.join(
            [packages_translating_the_same_msgid, os.environ.get('PYTHONPATH', '')]
        ),
        'BS_INSTALLED_APPS': json.dumps(['bazis.contrib.fake_second', 'bazis.contrib.fake_first']),
    }

    assert {seed: run_with_seed(code, seed, **env) for seed in SEEDS} == {
        seed: 'fake_second' for seed in SEEDS
    }


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

    assert {seed: run_with_seed(code, seed) for seed in SEEDS} == {
        seed: expected for seed in SEEDS
    }
