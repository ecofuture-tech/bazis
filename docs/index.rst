Bazis API Framework
=============================

.. toctree::
   :hidden:

   Home page <self>
   setting
   routes
   openapi
   structure

General Overview
----------------

**Bazis** is a framework designed for rapid API development. It combines the capabilities of Django and FastAPI to provide a flexible and reliable solution for creating APIs. Django is used as the foundation for ORM and the administrative panel, while FastAPI ensures high performance when handling API requests.

**This package serves as the core for other Bazis family packages.**

To add additional functionality, you can use packages named ``bazis-<name>``. All of these packages will require this core package.

Main Concept
------------
The **Bazis** framework is built around combining Django's ORM capabilities with FastAPI's high-performance API handling. This hybrid approach allows developers to utilize Django's robust database management tools and admin interface while benefiting from the speed and simplicity of FastAPI.

The central entity in a project built using Bazis is the Django model. Once its fields are defined, it provides enough information to generate a working CRUD API. For describing the API, the OpenAPI protocol is a perfect fit, into which Pydantic schemas can be automatically converted.

Thus, the framework's task is to transform model and route definitions into Pydantic schemas.

In Bazis, these Pydantic schemas are generated as follows:

- A route class is declared, specifying the target model.
- Optionally, field restrictions can be defined.
- Specific CRUD operations for the route can be optionally specified.
- Input and output Pydantic schemas are generated based on the route and related model.

Other Important Implementation Features
---------------------------------------
- **JSON:API** is chosen as the JSON protocol for interaction, which includes support for nested structures (``included``), multi-level filtering, and more.
- The project settings management system is implemented through ``django.conf.settings`` so that values can be set either via environment variables or in the admin panel:
  - For this purpose, each Bazis application defines a ``conf.py`` module containing a Pydantic ``Settings`` schema, which includes the configuration fields.
  - Therefore, filling in a standard ``settings.py`` file is not required (only an import of ``bazis.core.configure`` is needed). Instead, all variables are set declaratively.

Key Features of the Framework
-----------------------------
- **Hybrid Framework**: Combines Django and FastAPI.
- **JSON:API Specification**: Adheres to the JSON:API specification for building APIs.
- **Class-Based Routes**: Routes are defined as class methods.
- **Modular Design**: Easily extendable and customizable.
- **Settings Management System**: Implementation of ``django.conf.settings`` via environment and admin panel.

Advantages Over Other Solutions
-------------------------------
1. **Performance**: FastAPI's asynchronous capabilities provide high performance and low latency.
2. **Flexibility**: Combines the best aspects of Django and FastAPI.
3. **Ease of Use**: Simplifies the development process through class-based routes and dependency injection.
4. **Scalability**: Designed to handle large-scale applications.
5. **Standards Compliance**: Adheres to JSON:API and OpenAPI specifications to ensure consistency and interoperability.

Installation
------------
**Note!** The current implementation of the framework requires **Redis** as the cache backend and **PostgreSQL** as the database.

To install the Bazis framework in your project, run the following command:

.. code-block:: bash

    pip install bazis

Running a Test Project (Docker)
-------------------------------
0. The following must be installed in your system beforehand:
   - Git
   - Docker
   - PostgreSQL 12+

1. Clone the repository:

   .. code-block:: bash

       git clone git@github.com:ecofuture-tech/bazis.git

2. Navigate to the sample project folder:

   .. code-block:: bash

       cd bazis/sample

3. Configure the environment variables in the ``.env`` file:

   Detailed instructions for configuring the project can be found in the documentation:
   :doc:`setting`.

   Example ``.env`` file:

   .. code-block:: bash

       BS_DEBUG=true
       BS_SECRET_KEY=1232434535465476587689780999

       BS_HOST_URL=http://localhost:9000

       BS_APP_DOMAIN=localhost
       BS_APP_PORT=9000

       BS_ADMIN_DOMAIN=localhost
       BS_ADMIN_PORT=9001

       BS_DATABASES__DEFAULT__HOST=host.docker.internal
       BS_DATABASES__DEFAULT__PORT=5432
       BS_DATABASES__DEFAULT__NAME=bazis-sample-db
       BS_DATABASES__DEFAULT__USER=DB_USER
       BS_DATABASES__DEFAULT__PASSWORD=DB_PASSWORD

       BS_CACHES__DEFAULT__LOCATION=redis://:@redis:6379/1

       BS_ADMIN_NAME=admin
       BS_ADMIN_PASSWORD=qwer1234

4. Run docker compose:

   .. code-block:: bash

       docker compose --env-file ./.env --env-file ./project.env -f docker-compose.yml -f docker-compose.local.yml up --build

5. After starting, the admin panel and Swagger will be available at the following addresses:

- http://localhost:9000/admin/
- http://localhost:9001/api/swagger/


Running the Project for Bazis Development (Docker)
--------------------------------------------------

The process differs only at step 4 - instead of using ``docker-compose.local.yml``, ``docker-compose.dev.yml`` is used:

.. code-block:: bash

   docker compose --env-file ./.env --env-file ./project.env -f docker-compose.yml -f docker-compose.dev.yml up --build

This setup will install packages with linking instead of installing them from PyPI as usual.
Linkable packages are specified in ``sample/requirements.dev.txt``.


Bazis Framework Structure
=========================

The **bazis** package is the core required project installed under the ``bazis.core`` namespace.
Other extension packages will be installed under the ``bazis.contrib`` namespace.

Approximate Structure of Each Application
-----------------------------------------

(All files are optional):

- **models_abstract.py**: Mixins or abstractions for creating real models.
- **admin_abstract.py**: Mixins for creating admin classes.
- **routes_abstract.py**: Mixins and base classes for building class-based routes.
- **models.py**: Actual models required for the application.
- **admin.py**: Admin classes for the application.
- **routes.py**: Route classes for the application.
- **router.py**: Describes URL routing for the application.
- **schemas.py**: Static Pydantic schemas used in the module.
- **triggers.py**: The framework actively uses ``django-pgtrigger`` functionality. This module defines triggers required for the package.
- **services/services.py**: Dependency services connected in routing.

Features of Bazis Models
------------------------
- Every model and mixin must inherit from ``bazis.core.models_abstract.InitialBase``.
- The logic of missing the Meta class in a model has been changed:
  - By default in Django, if a model does not define a Meta class, the Meta parameters are considered unset.
  - Bazis adds the default inheritance functionality from all parent classes, meaning if the Meta class is not defined, the model will receive a composite Meta class from all parents in the order of model inheritance.

Dynamic Fields
--------------

.. toctree::
   :maxdepth: 3

   dynamic_fields
   sparse_fieldsets
   services
   response_models
   endpoint_callbacks
   relationships
