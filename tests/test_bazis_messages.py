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
`manage.py bazis_messages`: the catalogs of the project are made with the ignores of a
Bazis project, reported as JSON, filled from a JSON file (contexts and plurals) and
compiled; applying a file again changes nothing.
"""

import gettext
import json

from django.conf import settings
from django.core.management import CommandError, call_command

import pytest


MODELS = """
from django.utils.translation import gettext_lazy as _, ngettext_lazy, pgettext_lazy

TITLE = _('Open')
VERB = pgettext_lazy('verb', 'Open')
ITEMS = ngettext_lazy('%(n)s item', '%(n)s items', 'n')
HINT = _('A long text that the catalogs wrap on several lines: the file of the translations '
         'and makemessages must wrap it the same way, or every run would change the catalog')
"""
# texts of the directories that are not the code of the project
IGNORED = ['.venv/lib/pkg', 'venv', '.scratch', 'node_modules/pkg', 'frontend/src', 'media']
RU_PO = 'locale/ru/LC_MESSAGES/django.po'
LONG = (
    'A long text that the catalogs wrap on several lines: the file of the translations '
    'and makemessages must wrap it the same way, or every run would change the catalog'
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / 'shop').mkdir()
    (tmp_path / 'shop' / 'models.py').write_text(MODELS)
    for path in IGNORED:
        (tmp_path / path).mkdir(parents=True)
        (tmp_path / path / 'texts.py').write_text(f"_('Ignored {path}')\n")
    # not the fixture `settings`: see tests/test_request_language.py
    monkeypatch.setattr(settings, 'BASE_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    return tmp_path


def run(*args) -> dict:
    from io import StringIO

    out = StringIO()
    call_command('bazis_messages', *args, stdout=out)
    return json.loads(out.getvalue())


def write(path, data) -> str:
    path.write_text(json.dumps(data, ensure_ascii=False))
    return str(path)


def ru(project):
    return gettext.translation('django', str(project / 'locale'), ['ru'])


def test_make_reports_the_project_texts(project):
    status = run('make')
    # English is the language of the msgids: no catalog
    assert list(status) == ['ru']
    assert status['ru'] == {
        'catalogs': [RU_PO],
        'total': 4,
        'translated': 0,
        'untranslated': [
            {'msgid': 'Open'},
            {'msgid': 'Open', 'msgctxt': 'verb'},
            {'msgid': '%(n)s item', 'msgid_plural': '%(n)s items'},
            {'msgid': LONG},
        ],
        'fuzzy': [],
    }
    catalog = (project / RU_PO).read_text()
    assert 'Ignored' not in catalog
    assert run('status') == status
    # made again without changes
    assert run('make') == status
    assert (project / RU_PO).read_text() == catalog


def test_apply_and_compile(project, tmp_path):
    run('make')
    translations = write(
        tmp_path / 'ru.json',
        {
            'ru': [
                {'msgid': 'Open', 'msgstr': 'Открыть'},
                {'msgctxt': 'verb', 'msgid': 'Open', 'msgstr': 'Открыть (действие)'},
                {
                    'msgid': '%(n)s item',
                    'msgstr': ['%(n)s предмет', '%(n)s предмета', '%(n)s предметов'],
                },
                {'msgid': LONG, 'msgstr': 'Длинный текст, ' * 8},
                {'msgid': 'Missing', 'msgstr': 'Нет'},
            ]
        },
    )
    result = run('apply', translations)
    assert result == {
        'ru': {'applied': 4, 'unknown': [{'msgid': 'Missing'}], 'untranslated': 0, 'fuzzy': 0}
    }
    catalog = ru(project)
    assert catalog.gettext('Open') == 'Открыть'
    assert catalog.pgettext('verb', 'Open') == 'Открыть (действие)'
    assert catalog.ngettext('%(n)s item', '%(n)s items', 5) == '%(n)s предметов'
    assert '#, fuzzy' not in (project / RU_PO).read_text()

    # idempotent: the catalog is not written again
    before = (project / RU_PO).read_text()
    assert run('apply', translations)['ru']['applied'] == 0
    assert (project / RU_PO).read_text() == before
    # and makemessages keeps it as apply wrote it
    run('make')
    assert (project / RU_PO).read_text() == before
    # a msgid that is not in the catalogs fails the check
    with pytest.raises(CommandError, match='Incomplete translations: ru'):
        run('apply', translations, '--check')
    run('status', '--check')


def test_fuzzy_after_a_change_of_the_source(project, tmp_path):
    run('make')
    run('apply', write(tmp_path / 'ru.json', {'ru': {'Open': 'Открыть'}}))
    models = project / 'shop' / 'models.py'
    models.write_text(models.read_text().replace("_('Open')", "_('Open it')"))

    status = run('make')['ru']
    assert {'msgid': 'Open it', 'msgstr': 'Открыть'} in status['fuzzy']
    # the obsolete entries are dropped
    assert '#~' not in (project / RU_PO).read_text()
    with pytest.raises(CommandError, match='Incomplete translations: ru'):
        run('status', '--check')

    result = run('apply', write(tmp_path / 'ru.json', {'ru': {'Open it': 'Открыть его'}}))
    assert result['ru']['fuzzy'] == 0
    assert ru(project).gettext('Open it') == 'Открыть его'


@pytest.mark.parametrize(
    'data, message',
    [
        ({'de': {'Open': 'Öffnen'}}, 'Not languages of LANGUAGES: de'),
        ({'ru': 'Открыть'}, 'are an object or a list'),
        ({'ru': [{'msgid': 'Open'}]}, 'Not a translation of ru'),
        ({'ru': {'Open': 1}}, 'Not a translation of ru'),
        ({'ru': {'%(n)s item': 'предмет'}}, 'needs the list of its forms'),
        ({'ru': {'Open': ['Открыть']}}, 'its translation is a string'),
    ],
)
def test_apply_refuses(project, tmp_path, data, message):
    run('make')
    with pytest.raises(CommandError, match=message):
        run('apply', write(tmp_path / 'ru.json', data))


def test_languages(project):
    assert run('status', '-l', 'en') == {
        'en': {'catalogs': [], 'total': 0, 'translated': 0, 'untranslated': [], 'fuzzy': []}
    }
    with pytest.raises(CommandError, match='Not languages of LANGUAGES: de'):
        run('status', '-l', 'de')
    with pytest.raises(CommandError, match='apply needs the JSON file'):
        run('apply')


def test_compile_only_the_project(project):
    run('make')
    assert run('compile') == {'compiled': [RU_PO]}
    assert (project / 'locale/ru/LC_MESSAGES/django.mo').is_file()
