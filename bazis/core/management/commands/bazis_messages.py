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

import contextlib
import json
from fnmatch import fnmatchcase
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.utils import find_command, popen_wrapper
from django.utils.translation import to_locale

import polib


#: the directories of a project that hold no translatable code of its own: the virtual
#: environments, the scratch files, the frontend, the collected and uploaded files (Django
#: adds the hidden directories, `.*`, and MEDIA_ROOT and STATIC_ROOT)
IGNORE_PATTERNS = [
    '.venv',
    'venv',
    '.scratch',
    'node_modules',
    'frontend',
    'static',
    'media',
    'build',
    'dist',
]


class Command(BaseCommand):
    """
    The gettext catalogs (`django`) of the project: `<BASE_DIR>/locale` and the `locale`
    directories of the apps of the project, never the ones of the installed packages.

    - `make`: runs makemessages for the languages from BASE_DIR with the ignores of a Bazis
      project and without the obsolete entries, then prints the status;
    - `status`: prints, by language, the untranslated and the fuzzy entries as JSON;
    - `apply FILE`: sets the translations of a JSON file, removes their fuzzy flags and
      compiles the catalogs; prints the result. The file maps a language to the
      translations: `{"ru": {"<msgid>": "<msgstr>", "<msgid of a plural>": ["<form 0>",
      ...]}}`, or to a list of entries, which also give the context:
      `{"ru": [{"msgctxt": "<context>", "msgid": "<msgid>", "msgstr": "<msgstr>"}]}`.
      Applying the same file again changes nothing;
    - `compile`: compiles the catalogs (`msgfmt --check-format`).

    The languages are `--locale` (repeatable), by default the languages of LANGUAGES other
    than English (the msgids are English). `--check` fails when an entry stays untranslated
    or fuzzy, or (apply) a msgid of the file is not in the catalogs.

    Tags: RAG
    """

    help = 'Makes, reports, fills from a JSON file and compiles the catalogs of the project.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['make', 'status', 'apply', 'compile'])
        parser.add_argument('file', nargs='?', help='apply: the JSON file of the translations.')
        parser.add_argument(
            '-l',
            '--locale',
            action='append',
            dest='languages',
            help='A language of LANGUAGES (repeatable). Default: all but English.',
        )
        parser.add_argument(
            '-i',
            '--ignore',
            action='append',
            default=[],
            dest='ignore_patterns',
            help='make: also ignore the files and directories of this glob pattern.',
        )
        parser.add_argument(
            '--check',
            action='store_true',
            help='Fail when an entry is untranslated or fuzzy, or a msgid of the file unknown.',
        )

    def handle(self, *args, action, file, languages, ignore_patterns, check, **options):
        languages = _languages(languages)
        if action == 'apply':
            if not file:
                raise CommandError('apply needs the JSON file of the translations.')
            result = _apply(_read_translations(file, languages))
            languages = list(result)
        elif file:
            raise CommandError(f'{action} takes no file.')
        if action == 'make':
            _make(languages, IGNORE_PATTERNS + ignore_patterns)
        if action in ('apply', 'compile'):
            compiled = _compile(languages)
        if action == 'compile':
            result = {'compiled': compiled}
        else:
            status = _status(languages)
            if action == 'apply':
                for language, counts in result.items():
                    counts['untranslated'] = len(status[language]['untranslated'])
                    counts['fuzzy'] = len(status[language]['fuzzy'])
            else:
                result = status
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))

        if check and action != 'compile':
            failed = [
                language
                for language, it in result.items()
                if it['untranslated'] or it['fuzzy'] or it.get('unknown')
            ]
            if failed:
                raise CommandError(f'Incomplete translations: {", ".join(failed)}.')


def _languages(languages: list[str] | None) -> list[str]:
    codes = [code for code, _name in settings.LANGUAGES]
    if not languages:
        return [code for code in codes if code.split('-')[0] != 'en']
    if unknown := sorted(set(languages) - set(codes)):
        raise CommandError(f'Not languages of LANGUAGES: {", ".join(unknown)}.')
    return languages


def _base_dir() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _locale_dirs() -> list[Path]:
    """
    The 'locale' directories of the project: `<BASE_DIR>/locale` and the directories of
    LOCALE_PATHS under BASE_DIR outside the ignored ones (an environment in the project).
    """
    base = _base_dir()
    dirs = [base / 'locale']
    for path in map(Path, settings.LOCALE_PATHS):
        path = path.resolve()
        if path.is_relative_to(base) and path not in dirs and not _ignored(path.relative_to(base)):
            dirs.append(path)
    return dirs


def _ignored(path: Path) -> bool:
    return any(fnmatchcase(part, it) for part in path.parts for it in [*IGNORE_PATTERNS, '.*'])


def _catalogs(language: str) -> list[Path]:
    """The catalogs `django.po` of the language in the project."""
    paths = (it / to_locale(language) / 'LC_MESSAGES' / 'django.po' for it in _locale_dirs())
    return [it for it in paths if it.is_file()]


def _relative(path: Path) -> str:
    return str(path.relative_to(_base_dir()))


def _entry(entry: polib.POEntry, *, msgstr: bool = False) -> dict:
    """An entry for the JSON: the format of the file of apply, with its current msgstr."""
    data = {'msgid': entry.msgid}
    if entry.msgctxt is not None:
        data['msgctxt'] = entry.msgctxt
    if entry.msgid_plural:
        data['msgid_plural'] = entry.msgid_plural
    if msgstr:
        data['msgstr'] = (
            [entry.msgstr_plural[i] for i in sorted(entry.msgstr_plural)]
            if entry.msgid_plural
            else entry.msgstr
        )
    return data


def _status(languages: list[str]) -> dict:
    status = {}
    for language in languages:
        catalogs = _catalogs(language)
        untranslated, fuzzy, total = [], [], 0
        for path in catalogs:
            po = polib.pofile(str(path))
            total += len([it for it in po if not it.obsolete])
            untranslated += [_entry(it) for it in po.untranslated_entries()]
            fuzzy += [_entry(it, msgstr=True) for it in po.fuzzy_entries()]
        status[language] = {
            'catalogs': [_relative(it) for it in catalogs],
            'total': total,
            'translated': total - len(untranslated) - len(fuzzy),
            'untranslated': untranslated,
            'fuzzy': fuzzy,
        }
    return status


def _make(languages: list[str], ignore_patterns: list[str]):
    base = _base_dir()
    # the catalogs of the project: makemessages stores the messages of a file in the
    # nearest 'locale' directory, else in the first one of LOCALE_PATHS (of a package)
    (base / 'locale').mkdir(exist_ok=True)
    with contextlib.chdir(base):
        call_command(
            'makemessages',
            locale=[to_locale(it) for it in languages],
            domain='django',
            ignore_patterns=ignore_patterns,
            no_obsolete=True,
            verbosity=0,
        )


def _read_translations(file: str, languages: list[str]) -> dict[str, list[tuple]]:
    """
    The translations of the file by language: (msgctxt, msgid, msgstr) with a list of the
    forms as msgstr of a plural.
    """
    try:
        with open(file, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise CommandError(f'Cannot read {file}: {e}') from None
    if not isinstance(data, dict):
        raise CommandError('The file maps the languages to their translations.')
    _languages(list(data))

    translations = {}
    for language, items in data.items():
        if isinstance(items, dict):
            items = [{'msgid': k, 'msgstr': v} for k, v in items.items()]
        if not isinstance(items, list):
            raise CommandError(f'The translations of {language} are an object or a list.')
        for item in items:
            if not _is_translation(item):
                raise CommandError(f'Not a translation of {language}: {item!r}.')
        translations[language] = [(it.get('msgctxt'), it['msgid'], it['msgstr']) for it in items]
    return translations


def _is_translation(item) -> bool:
    if not isinstance(item, dict):
        return False
    msgstr = item.get('msgstr')
    return (
        isinstance(item.get('msgid'), str)
        and isinstance(item.get('msgctxt', ''), str)
        and (
            isinstance(msgstr, str)
            or (isinstance(msgstr, list) and all(isinstance(it, str) for it in msgstr))
        )
    )


def _set(entry: polib.POEntry, msgstr: str | list[str]) -> bool:
    """Sets the translation of the entry; whether the entry changed."""
    if entry.msgid_plural:
        if not isinstance(msgstr, list):
            raise CommandError(f'The plural {entry.msgid!r} needs the list of its forms.')
        value = dict(enumerate(msgstr))
        if entry.msgstr_plural == value and not entry.fuzzy:
            return False
        entry.msgstr_plural = value
    else:
        if not isinstance(msgstr, str):
            raise CommandError(f'{entry.msgid!r} is not a plural: its translation is a string.')
        if entry.msgstr == msgstr and not entry.fuzzy:
            return False
        entry.msgstr = msgstr
    if entry.fuzzy:
        entry.flags.remove('fuzzy')
    entry.previous_msgctxt = entry.previous_msgid = entry.previous_msgid_plural = None
    return True


def _apply(translations: dict[str, list[tuple]]) -> dict:
    result = {}
    for language, items in translations.items():
        catalogs = [(path, polib.pofile(str(path))) for path in _catalogs(language)]
        applied, unknown, changed = 0, [], set()
        for msgctxt, msgid, msgstr in items:
            # an empty translation is no translation
            if not msgstr or (isinstance(msgstr, list) and not all(msgstr)):
                continue
            found = False
            for path, po in catalogs:
                if (entry := po.find(msgid, msgctxt=msgctxt)) is None or entry.obsolete:
                    continue
                found = True
                if _set(entry, msgstr):
                    changed.add(path)
                    applied += 1
            if not found:
                unknown.append({'msgid': msgid} | ({'msgctxt': msgctxt} if msgctxt else {}))
        for path, po in catalogs:
            # a new catalog of makemessages: its header is fuzzy and has no language
            if po.metadata_is_fuzzy or not po.metadata.get('Language'):
                po.metadata_is_fuzzy = False
                po.metadata['Language'] = to_locale(language)
                changed.add(path)
            if path in changed:
                po.save()
                # the layout of gettext (makemessages), not of polib: a run of makemessages
                # after apply does not change the catalog
                _gettext('msgcat', '-o', str(path), str(path))
        result[language] = {'applied': applied, 'unknown': unknown}
    return result


def _gettext(program: str, *args: str):
    if find_command(program) is None:
        raise CommandError(f'{program} of GNU gettext is not installed.')
    __, errors, status = popen_wrapper([program, *args])
    if status:
        raise CommandError(f'{program} failed:\n{errors}')


def _compile(languages: list[str]) -> list[str]:
    compiled = []
    for language in languages:
        for path in _catalogs(language):
            _gettext('msgfmt', '--check-format', '-o', str(path.with_suffix('.mo')), str(path))
            compiled.append(_relative(path))
    return compiled
