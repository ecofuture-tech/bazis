Project Configuration
=====================

To use the functionality described in this section:

- In the Django settings file **{PROJECT_NAME}/settings.py**, import **bazis.core.configure**:

.. code-block:: python

    import bazis.core.configure # noqa: F401

The project configuration is organized so that all configuration parameters are accessible in the standard Django way:

.. code-block:: python

    from django.conf import settings
    print(settings.DEBUG)

Configuration parameters at the Bazis level are stored in conf.py files inside Bazis applications.
Configuration parameters at the project level are stored in the conf.py file inside the target project folder, where files such as settings.py, urls.py, etc., are usually located.

Settings of the Bazis packages
------------------------------

The conf.py modules of all Bazis packages installed in the environment (``bazis.contrib.<name>``) are loaded, also of the packages the project does not use. A setting is read from its ``BS_*`` variable only if a conf.py declares it, so:

- the core (``bazis.core.conf``) declares the settings of Django that a project sets with ``BS_*``, with the defaults of Django, including ``AUTH_USER_MODEL`` (``auth.User``) and ``AUTHENTICATION_BACKENDS``; the project sets them, e.g. ``BS_AUTH_USER_MODEL=users.User``;
- a package declares only the settings it owns (``BAZIS_*``, ``KAFKA_*``, or names of its own such as ``AUTH_ANONYMOUS_USER_MODEL`` of bazis-users), which have no effect without the code of the package, and never redeclares or defaults a setting of Django. bazis-users and bazis-authing drop their ``AUTH_USER_MODEL`` and ``AUTHENTICATION_BACKENDS`` in their next releases, which require this version of the core.

``BS_BAZIS_APPS`` (or ``BS_BAZIS_CONFIG_APPS``) is only an explicit override: the exact list of the packages to load the settings from.

.. code-block:: bash

    BS_BAZIS_APPS='["bazis.contrib.users", "bazis.contrib.permit"]'

Leave it unset in projects. An empty list (``'[]'``) turns off the settings of all Bazis packages, also of the ones the project uses, and is a configuration error unless intended: the system check ``bazis.W002`` (``manage.py bazis_doctor``) warns about it.

Structure of the conf.py file
-----------------------------

The file must contain a Settings class inherited from :py:class:`~bazis.core.utils.schemas.BazisSettings`.

.. code-block:: python

    class Settings(BazisSettings):
        ...

A global variable `settings` is also created, which is needed for autonomous testing of the package.

.. code-block:: python

    settings = Settings()

Configuration class parameters are declared according to pydantic rules.
Settings parameters are of two types:

- Static: values will be pulled from .env and project.env (more details below)
- Dynamic: values can be overridden in the Django admin panel

To declare a dynamic parameter, use the Field class and set the attribute dynamic=True.

Dynamic Configuration Parameters
--------------------------------

If the dynamic=True attribute is set in Field, the parameter will be dynamically changeable.
Its value can be changed through the project admin panel.
Internally, this is implemented through the constance library.
For example, the parameter is defined as follows:

.. code-block:: python

    BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT: int = Field(
        20, title=_('Default number of results in the list'), dynamic=True
    )

Thus, when requesting settings.BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT, a call to getattr(constance.config, 'BAZIS_API_PAGINATION_PAGE_SIZE_DEFAULT') is actually made.

Static Configuration Parameters
-------------------------------

If the dynamic=True attribute is absent in Field, the parameter will be set from the \*.env files.
Currently, the following files are supported:

- **.env**: contains project settings values specific to the current environment. Not included in git
- **project.env**: contains project settings values common to all environments. Included in git

Environment variable names in \*.env files must start with the prefix BS\_.

Database and cache configuration is currently fully assembled from the config. Therefore, nested fields (database name, user name, etc.) need to be specified in the environment. This can be done as follows:

.. code-block:: none

    BS_DATABASES__DEFAULT__HOST=192.168.56.104
    BS_DATABASES__DEFAULT__PORT=5433
    BS_DATABASES__DEFAULT__NAME=smart-waste
    BS_DATABASES__DEFAULT__USER=sw
    BS_DATABASES__DEFAULT__PASSWORD=sw

Similarly for the cache. Bazis requires Redis (django-redis): model items are cached and
invalidated by key pattern, which other Django cache backends do not support. The system
check ``bazis.E001`` reports another backend. For example:

.. code-block:: none

    BS_CACHES__DEFAULT__BACKEND=django_redis.cache.RedisCache
    BS_CACHES__DEFAULT__LOCATION=redis://redis:6379/1

Note that **...__DEFAULT__...** is specified in uppercase - this is a server deployment requirement.
In the Bazis configuration, an alias is used to convert to lowercase:

.. code-block:: python

    class DatabaseDefault(BaseModel):
        default: Database = Field(Database(), alias='DEFAULT')

Required Security Settings
--------------------------

``BS_SECRET_KEY`` must be set in the environment of every project deployment and be the
same for all processes of the deployment: sessions, CSRF tokens and signed data depend on it.
The key must be at least 32 characters long, contain at least 5 unique characters and
must not be a ``django-insecure-`` development key. Generate one, for example, with:

.. code-block:: bash

    python -c "import secrets; print(secrets.token_urlsafe(50))"

With ``BS_DEBUG=false`` an absent or weak key stops the application at startup with
``ImproperlyConfigured``. With ``BS_DEBUG=true`` a warning is logged, and an absent key is
replaced by a temporary random one, which changes on every start.

``BS_DEBUG`` must be ``false`` in production: with DEBUG enabled error responses include
tracebacks and the OpenAPI documentation is published.

``BS_ALLOWED_HOSTS`` defaults to ``["*"]``. The wildcard is removed as soon as concrete hosts
are configured (in the environment, in ``settings.py`` or through ``BS_APP_DOMAIN`` /
``BS_ADMIN_DOMAIN``), so that it does not disable host validation.

Email Settings
--------------

Django 6.1 deprecates the ``EMAIL_*`` settings in favour of ``MAILERS`` (they are removed
in Django 7.0). Bazis configures ``MAILERS['default']`` with ``BAZIS_EMAIL_BACKEND``
(``bazis.core.mail.DynamicSMTPEmailBackend`` by default), which reads the SMTP parameters
from the dynamic settings every time a connection is created, so they can be changed
in the admin panel:

.. code-block:: none

    BS_BAZIS_EMAIL_HOST=smtp.example.com
    BS_BAZIS_EMAIL_PORT=587
    BS_BAZIS_EMAIL_HOST_USER=user
    BS_BAZIS_EMAIL_HOST_PASSWORD=password
    BS_BAZIS_EMAIL_USE_TLS=true
    BS_BAZIS_EMAIL_USE_SSL=false
    BS_DEFAULT_FROM_EMAIL=noreply@example.com

For development, the messages can be printed instead of sent:

.. code-block:: none

    BS_BAZIS_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

The former variables (``BS_EMAIL_HOST`` and others) are still read, with a deprecation
warning, and the values stored in the admin panel are moved to the new names by the
``core.0003_rename_email_settings`` migration. If a project defines the ``EMAIL_*``
settings in its ``settings.py``, Bazis does not configure ``MAILERS``: Django does not
allow combining them.

Schema Cache
------------

Bazis generates Pydantic schemas per route, action and combination of included resources.
Schemas that are not used for ``BS_BAZIS_SCHEMA_CACHE_TTL`` seconds (3600 by default) are
removed from the cache and generated again on demand; ``0`` keeps them forever.

Notes
-----

When running on MacOS, additional library search paths may need to be specified. For example, for GDAL and GEOS (version numbers may differ):

BS_GDAL_LIBRARY_PATH=/opt/homebrew/Cellar/gdal/3.9.0/lib/libgdal.dylib
BS_GEOS_LIBRARY_PATH=/opt/homebrew/Cellar/geos/3.12.1/lib/libgeos_c.dylib
