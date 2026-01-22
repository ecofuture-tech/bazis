Project Configuration
=====================

To use the functionality described in this section:

- In the Django settings file **{PROJECT_NAME}/settings.py**, import **bazis.core.configure**:

.. code-block:: python

    import bazis.core.configure

The project configuration is organized so that all configuration parameters are accessible in the standard Django way:

.. code-block:: python

    from django.conf import settings
    print(settings.DEBUG)

Configuration parameters at the Bazis level are stored in conf.py files inside Bazis applications.
Configuration parameters at the project level are stored in the conf.py file inside the target project folder, where files such as settings.py, urls.py, etc., are usually located.

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

Similarly for the cache, for example:

.. code-block:: none

    BS_CACHES__DEFAULT__BACKEND=django.core.cache.backends.locmem.LocMemCache

Note that **...__DEFAULT__...** is specified in uppercase - this is a server deployment requirement.
In the Bazis configuration, an alias is used to convert to lowercase:

.. code-block:: python

    class DatabaseDefault(BaseModel):
        default: Database = Field(Database(), alias='DEFAULT')

Notes
-----

When running on MacOS, additional library search paths may need to be specified. For example, for GDAL and GEOS (version numbers may differ):

BS_GDAL_LIBRARY_PATH=/opt/homebrew/Cellar/gdal/3.9.0/lib/libgdal.dylib
BS_GEOS_LIBRARY_PATH=/opt/homebrew/Cellar/geos/3.12.1/lib/libgeos_c.dylib
