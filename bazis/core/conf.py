import decimal
from secrets import token_hex

from django.utils.translation import gettext_lazy as _

from pydantic import BaseModel, Field, model_validator

import pytz

from bazis.core.utils.schemas import BazisSettings


def secret_key_generate():
    """
    Generates cryptographically secure random secret key.
    Uses secrets.token_hex() for Django SECRET_KEY generation.
    """
    return token_hex()


class Database(BaseModel):
    """
    PostgreSQL/PostGIS database configuration schema.
    Default engine: PostGIS backend for geographic data support.

    Fields:
    - ENGINE: Database backend (default: PostGIS)
    - CONN_MAX_AGE: Connection pooling timeout in seconds
    - CONN_HEALTH_CHECKS: Enable connection health validation
    - HOST, PORT, NAME, USER, PASSWORD: Connection credentials
    """

    ENGINE: str = 'django.contrib.gis.db.backends.postgis'
    CONN_MAX_AGE: float = 60.0
    CONN_HEALTH_CHECKS: bool = True
    HOST: str = ''
    PORT: str = ''
    NAME: str = 'default'
    USER: str = ''
    PASSWORD: str = ''

    @property
    def PSYCOPG3_PARAMS(self):  # noqa: N802
        """
        Returns psycopg3 connection parameters dictionary.
        Used for direct PostgreSQL connections outside Django ORM.
        """
        return {
            'dbname': self.NAME,
            'user': self.USER,
            'password': self.PASSWORD,
            'host': self.HOST,
            'port': self.PORT,
        }

    def model_dump(self, *args, **kwargs):
        """
        Serializes model including @property fields.
        Overrides default Pydantic serialization to export computed properties.
        """
        d = super().model_dump(*args, **kwargs)
        for name in dir(self):
            if name.startswith('_'):
                continue
            attr = getattr(type(self), name, None)
            if isinstance(attr, property):
                d[name] = getattr(self, name)
        return d


class DatabaseDefault(BaseModel):
    """
    Wrapper for default database configuration.
    Maps Django's DATABASES['default'] structure.
    """

    default: Database = Field(Database(), alias='DEFAULT')


class CacheOptions(BaseModel):
    """
    Redis cache backend options for django-redis.

    Fields:
    - CLIENT_CLASS: Redis client implementation
    - IGNORE_EXCEPTIONS: Continue on cache failures
    - MAX_ENTRIES: Maximum cache entries (default: 64k)
    """

    CLIENT_CLASS: str = 'django_redis.client.DefaultClient'
    IGNORE_EXCEPTIONS: bool = True
    MAX_ENTRIES: int = 65536


class Cache(BaseModel):
    """
    Cache backend configuration schema.
    Supports Django cache backends: LocMem, Redis, Memcached, etc.

    Fields:
    - BACKEND: Cache backend class path
    - LOCATION: Cache server address or identifier
    - TIMEOUT: Default cache TTL in seconds
    - OPTIONS: Backend-specific options
    """

    BACKEND: str = 'django.core.cache.backends.locmem.LocMemCache'
    LOCATION: str = ''
    TIMEOUT: int = 300
    OPTIONS: CacheOptions = CacheOptions()


class CacheDefault(BaseModel):
    """
    Wrapper for default cache configuration.
    Maps Django's CACHES['default'] structure.
    """

    default: Cache = Field(Cache(), alias='DEFAULT')


class Settings(BazisSettings):
    """
    Main Bazis framework settings schema extending BazisSettings.
    Combines Django, FastAPI, and framework-specific configurations.

    Key sections:
    - Django core: DEBUG, SECRET_KEY, DATABASES, MIDDLEWARE
    - URLs/Domains: APP_DOMAIN, ADMIN_DOMAIN, HOST_URL
    - Static/Media: STATIC_URL, MEDIA_URL, file paths
    - Framework: BAZIS_APPS, pagination, schema generation
    - Email: SMTP configuration
    - Geodjango: GDAL/GEOS library paths
    - Dynamic settings: Configurable via CONSTANCE

    Tags: RAG, EXPORT
    """

    DEBUG: bool = True
    BASE_DIR: str = ''
    APP_DOMAIN: str = ''
    ADMIN_DOMAIN: str = ''
    APP_PORT: int = Field(11000, title=_('Application port'))
    ADMIN_PORT: int = Field(11001, title=_('Admin port'))
    INSTALLED_APPS: list[str] = []
    BAZIS_APPS: list[str] = []
    MIDDLEWARE: list[str] = []
    BAZIS_MIDDLEWARES: list[str] = []
    LANGUAGES: list[tuple[str, str]] = [('en', 'English')]
    ROOT_URLCONF: str = ''
    TEMPLATES: list[dict] = []
    WSGI_APPLICATION: str = ''
    DEFAULT_AUTO_FIELD: str = 'django.db.models.BigAutoField'
    AUTH_PASSWORD_VALIDATORS: list[dict] = []
    SECRET_KEY: str = Field(default_factory=secret_key_generate, title=_('Secret key'))
    HOST_URL: str = ''
    ADMIN_HOST_URL: str = ''
    MEDIA_HOST_URL: str | None = Field(None, title=_('Media URL'))
    ADMIN_PATH: str = Field('admin', title=_('Admin path'))
    STATIC_URL: str = '/static/'
    MEDIA_URL: str = '/media/'
    STATIC_ROOT: str = '/tmp/static'
    MEDIA_ROOT: str = '/tmp/media'
    LANGUAGE_CODE: str = 'en-EN'
    TIME_ZONE: str = 'Etc/UTC'
    USE_I18N: bool = True
    USE_TZ: bool = True
    ALLOWED_HOSTS: list[str] = ['*']
    SENTRY_DSN: str = ''
    ENVIRONMENT_NAME: str = ''
    SERVER_NAME: str = ''
    RELEASE_VERSION: str = ''
    PGTRIGGER_INSTALL_ON_MIGRATE: bool = False
    PGTRIGGER_MIGRATIONS: bool = False
    DATABASES: DatabaseDefault = DatabaseDefault()
    CACHES: CacheDefault = CacheDefault()
    DATA_UPLOAD_MAX_MEMORY_SIZE: int = Field(
        20 * 1024 * 1024,
        title=_('Maximum request body size in bytes'),
        json_schema_extra={'dynamic': True},
    )
    CSRF_TRUSTED_ORIGINS: list[str] = Field([], title=_('Trusted schemes'))
    BAZIS_APP_MODULE: str = ''
    BAZIS_ROUTER_MODULE: str = ''
    BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT: int = Field(
        20, title=_('Default number of results in the list'), json_schema_extra={'dynamic': True}
    )
    BAZIS_API_PAGINATION_PAGE_SIZE_MAX: int = Field(
        1000, title=_('Maximum number of results in the list'), json_schema_extra={'dynamic': True}
    )
    CONSTANCE_DATABASE_CACHE_BACKEND: str | None = Field(
        None, title=_('Default cache instance for storing CONSTANCE')
    )
    CONSTANCE_ADDITIONAL_FIELDS: dict = {
        'timezone_select': [
            'django.forms.fields.ChoiceField',
            {
                'widget': 'django.forms.Select',
                'choices': [(tz, tz) for tz in pytz.common_timezones],
            },
        ],
    }
    GDAL_LIBRARY_PATH: str | None = Field(None, title=_('Path to the GDAL library'))
    GEOS_LIBRARY_PATH: str | None = Field(None, title=_('Path to the GEOS library'))
    BAZIS_DECIMAL_HALF: str = Field(
        decimal.ROUND_HALF_UP, title=_('Decimal rounding'), json_schema_extra={'dynamic': True}
    )
    BAZIS_APP_RELOAD_DIRS: list[str] = Field([], title=_('Directories to reload on change'))
    BAZIS_SCHEMA_WITHOUT_REF: bool = Field(True, title=_('Use $ref in OpenAPI schema'))

    # Email/SMTP configuration
    EMAIL_BACKEND: str = Field(
        'django.core.mail.backends.smtp.EmailBackend',
        title=_('Mail server backend'),
    )
    EMAIL_HOST: str = Field(
        '',
        title=_('Mail server IP address'),
        json_schema_extra={'dynamic': True},
    )
    EMAIL_PORT: str = Field(
        '',
        title=_('Mail server port number'),
        json_schema_extra={'dynamic': True},
    )
    EMAIL_HOST_USER: str = Field(
        '',
        title=_('Mail server user login'),
        json_schema_extra={'dynamic': True},
    )
    EMAIL_HOST_PASSWORD: str = Field(
        '',
        title=_('Mail server user password'),
        json_schema_extra={'dynamic': True},
    )
    EMAIL_USE_TLS: bool = Field(
        False,
        title=_('Mail server use TLS'),
        json_schema_extra={'dynamic': True},
    )
    EMAIL_USE_SSL: bool = Field(
        False,
        title=_('Mail server use SSL'),
        json_schema_extra={'dynamic': True},
    )
    DEFAULT_FROM_EMAIL: str = Field(
        '',
        title=_('Default outgoing email address'),
        json_schema_extra={'dynamic': True},
    )
    BAZIS_EXPORT_SETTINGS: list[str] = Field([], title=_('Export settings'))
    BAZIS_LIST_ID_LIMIT: int = Field(10000, title=_('Maximum IDs in list route'))

    @model_validator(mode='after')
    def calc_trusted_uri(self):
        """
        Auto-configures ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
        Adds APP_DOMAIN and ADMIN_DOMAIN to allowed hosts.
        Adds HOST_URL and ADMIN_HOST_URL to CSRF trusted origins.
        Removes wildcard '*' if specific hosts are configured.

        RAG keywords: validator, allowed hosts, csrf, security, auto-configuration
        """
        if self.APP_DOMAIN and self.APP_DOMAIN not in self.ALLOWED_HOSTS:
            self.ALLOWED_HOSTS.append(self.APP_DOMAIN)
        if self.ADMIN_DOMAIN and self.ADMIN_DOMAIN not in self.ALLOWED_HOSTS:
            self.ALLOWED_HOSTS.append(self.ADMIN_DOMAIN)

        if len(self.ALLOWED_HOSTS) > 1 and '*' in self.ALLOWED_HOSTS:
            self.ALLOWED_HOSTS.remove('*')

        if self.HOST_URL and self.HOST_URL not in self.CSRF_TRUSTED_ORIGINS:
            self.CSRF_TRUSTED_ORIGINS.append(self.HOST_URL)
        if self.ADMIN_HOST_URL and self.ADMIN_HOST_URL not in self.CSRF_TRUSTED_ORIGINS:
            self.CSRF_TRUSTED_ORIGINS.append(self.ADMIN_HOST_URL)

        return self


# Global settings instance loaded from environment variables
settings = Settings()
