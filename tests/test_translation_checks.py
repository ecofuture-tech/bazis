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
The checks of the translations of the Bazis packages: a msgid translated differently by two
packages (`bazis.W004`) and a language of the project the packages are not translated into
(`bazis.W005`).
"""

import sys
import types
from importlib.machinery import ModuleSpec

from django.conf import settings
from django.utils.translation import trans_real

import pytest

import bazis
from bazis.core import checks

from .utils.catalogs import write_mo


@pytest.fixture
def catalogs(tmp_path, monkeypatch):
    """
    Two Bazis packages, `bazis.contrib.fake_first` (installed) and `fake_second` (not
    installed), and a project, with their Russian catalogs; returns a function that writes
    a catalog: `write(<package or 'project'>, language, messages)`.
    """
    contrib = tmp_path / 'contrib'
    for name in ('fake_first', 'fake_second'):
        (contrib / name).mkdir(parents=True)
        (contrib / name / '__init__.py').write_text('')
    fake = types.ModuleType('bazis.contrib')
    fake.__path__ = [str(contrib)]
    fake.__spec__ = ModuleSpec('bazis.contrib', None, is_package=True)
    fake.__spec__.submodule_search_locations = fake.__path__
    monkeypatch.setitem(sys.modules, 'bazis.contrib', fake)
    monkeypatch.setattr(bazis, 'contrib', fake, raising=False)

    roots = {
        'project': tmp_path / 'project',
        'fake_first': contrib / 'fake_first',
        'fake_second': contrib / 'fake_second',
    }
    # not with the fixture `settings`: see test_request_language
    monkeypatch.setattr(settings, 'BASE_DIR', str(roots['project']))
    monkeypatch.setattr(settings, 'LOCALE_PATHS', [str(root / 'locale') for root in roots.values()])
    monkeypatch.setattr(settings, 'INSTALLED_APPS', ['bazis.contrib.fake_first'])
    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    monkeypatch.setattr(trans_real, '_translations', {})

    def write(owner: str, language: str, messages: dict[str, str]) -> None:
        write_mo(roots[owner] / 'locale' / language / 'LC_MESSAGES' / 'django.mo', messages)

    write('fake_first', 'ru', {'Fake name': 'Название', 'Fake save': 'Сохранить'})
    write('fake_second', 'ru', {'Fake name': 'Наименование', 'Fake save': 'Сохранить'})
    return write


def test_a_msgid_translated_differently(catalogs):
    [warning] = checks.check_translation_conflicts(None)

    assert warning.id == 'bazis.W004'
    assert warning.msg == (
        '"Fake name" is translated into ru differently by the Bazis packages: '
        'bazis.contrib.fake_first "Название", bazis.contrib.fake_second "Наименование"; '
        'the first one wins.'
    )


def test_a_msgid_the_project_translates(catalogs):
    catalogs('project', 'ru', {'Fake name': 'Имя'})

    assert checks.check_translation_conflicts(None) == []


def test_a_language_the_packages_are_not_translated_into(catalogs, monkeypatch):
    monkeypatch.setattr(
        settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский'), ('de', 'Deutsch')]
    )

    [warning] = checks.check_translations_of_languages(None)

    # the package that is not installed and English (the msgids) are not reported
    assert warning.id == 'bazis.W005'
    assert warning.msg == (
        'The language de of LANGUAGES has no translation of texts of the Bazis packages '
        'bazis.contrib.fake_first (2): they stay in English.'
    )

    # translated by the project
    catalogs('project', 'de', {'Fake name': 'Name', 'Fake save': 'Speichern'})
    monkeypatch.setattr(trans_real, '_translations', {})

    assert checks.check_translations_of_languages(None) == []
