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
Django 6.1 deprecates the EMAIL_* settings in favour of MAILERS, so the dynamic email
settings of Bazis are renamed to BAZIS_EMAIL_*. The values stored in Constance are
moved to the new keys, unless a value for the new key already exists.
"""

from django.conf import settings
from django.db import migrations


RENAMED_KEYS = {
    'EMAIL_HOST': 'BAZIS_EMAIL_HOST',
    'EMAIL_PORT': 'BAZIS_EMAIL_PORT',
    'EMAIL_HOST_USER': 'BAZIS_EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD': 'BAZIS_EMAIL_HOST_PASSWORD',
    'EMAIL_USE_TLS': 'BAZIS_EMAIL_USE_TLS',
    'EMAIL_USE_SSL': 'BAZIS_EMAIL_USE_SSL',
}


def rename_keys(schema_editor, renames: dict[str, str]):
    # raw SQL, as in 0002: the Constance model may change in the future;
    # the database backend of Constance stores the keys with an optional prefix
    prefix = getattr(settings, 'CONSTANCE_DATABASE_PREFIX', '')
    with schema_editor.connection.cursor() as cursor:
        for old_key, new_key in renames.items():
            old_key, new_key = f'{prefix}{old_key}', f'{prefix}{new_key}'
            cursor.execute(
                'UPDATE constance_constance SET key = %s WHERE key = %s '
                'AND NOT EXISTS (SELECT 1 FROM constance_constance WHERE key = %s)',
                [new_key, old_key, new_key],
            )


def forwards(apps, schema_editor):
    rename_keys(schema_editor, RENAMED_KEYS)


def backwards(apps, schema_editor):
    rename_keys(schema_editor, {new: old for old, new in RENAMED_KEYS.items()})


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_auto_20260114_1222'),
        ('constance', '0003_drop_pickle'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
