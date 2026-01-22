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

import sys

import bazis.core.configure  # noqa: F401


if 'pytest' in sys.modules:
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'sql': {
                'level': 'DEBUG',
                'class': 'logging.FileHandler',
                'filename': 'sql.log',
            },
        },
        'loggers': {
            'django.db.backends': {
                'level': 'DEBUG',
                'handlers': ['sql'],
                'propagate': False,
            },
        },
    }
