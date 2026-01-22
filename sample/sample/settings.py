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
