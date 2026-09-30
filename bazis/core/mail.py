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
Email delivery with SMTP settings editable at runtime.

Django 6.1 replaces the ``EMAIL_*`` settings with ``MAILERS``. Bazis keeps the SMTP
parameters as dynamic settings (``BAZIS_EMAIL_*``, stored in Constance and editable in
the admin) and configures the default mailer with ``DynamicSMTPEmailBackend``, which
reads them every time a connection is created.

Tags: RAG, EXPORT
"""

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend


# Bazis setting -> SMTP backend option
DYNAMIC_SMTP_OPTIONS = {
    'BAZIS_EMAIL_HOST': 'host',
    'BAZIS_EMAIL_PORT': 'port',
    'BAZIS_EMAIL_HOST_USER': 'username',
    'BAZIS_EMAIL_HOST_PASSWORD': 'password',
    'BAZIS_EMAIL_USE_TLS': 'use_tls',
    'BAZIS_EMAIL_USE_SSL': 'use_ssl',
}

def get_dynamic_smtp_options() -> dict:
    """
    Returns the SMTP backend options from the current values of the Bazis settings.
    """
    options = {option: getattr(settings, name) for name, option in DYNAMIC_SMTP_OPTIONS.items()}
    port = options['port']
    options['port'] = int(port) if port not in (None, '') else None
    return options


class DynamicSMTPEmailBackend(EmailBackend):
    """
    SMTP backend configured from the dynamic ``BAZIS_EMAIL_*`` settings.
    Options set explicitly in ``MAILERS`` take precedence over the settings.

    Tags: RAG, EXPORT
    """

    def __init__(self, **kwargs):
        super().__init__(**(get_dynamic_smtp_options() | kwargs))
