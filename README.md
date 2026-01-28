# Bazis

[![PyPI version](https://img.shields.io/pypi/v/bazis.svg)](https://pypi.org/project/bazis/)
[![Python Versions](https://img.shields.io/pypi/pyversions/bazis.svg)](https://pypi.org/project/bazis/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A framework for rapid API development that combines the capabilities of Django and FastAPI to create flexible and high-performance solutions.

## Quick Start

```bash
# Install the package
uv add bazis

# Create a model
from bazis.core.models_abstract import InitialBase
from django.db import models

class Organization(InitialBase):
    name = models.CharField(max_length=255)

# Create a route
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from django.apps import apps

class OrganizationRouteSet(JsonapiRouteBase):
    model = apps.get_model('myapp.Organization')
```

## Table of Contents

- [Description](#description)
- [Core Concept](#core-concept)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Deployment](#deployment)
- [Auto-Documentation](#auto-documentation)
- [Usage](#usage)
  - [Creating Models](#creating-models)
  - [Creating Routes](#creating-routes)
  - [Registering Routes](#registering-routes)
  - [Project Configuration](#project-configuration)
- [API Features](#api-features)
  - [Data Schema Analysis](#data-schema-analysis)
  - [Filtering](#filtering)
  - [Included Resources (JSON:API)](#included-resources-jsonapi)
  - [Error Format](#error-format)
- [Examples](#examples)
- [Architecture](#architecture)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Links](#links)

## Description

**Bazis** is a framework designed for rapid API development. It combines the capabilities of Django and FastAPI to provide a flexible and reliable solution for creating APIs. Django is used as the foundation for ORM and the administrative panel, while FastAPI ensures high performance when handling API requests.

**This package serves as the core for other Bazis family packages.**

To add additional functionality, you can use packages named `bazis-<n>`. All of these packages will require this core package.

## Core Concept

The **Bazis** framework is built around combining Django's ORM capabilities with FastAPI's high-performance API handling. This hybrid approach allows developers to utilize Django's robust database management tools and admin interface while benefiting from the speed and simplicity of FastAPI.

The central entity in a project built using Bazis is the Django model. Once its fields are defined, it provides enough information to generate a working CRUD API. For describing the API, the OpenAPI protocol is a perfect fit, into which Pydantic schemas can be automatically converted.

Thus, the framework's task is to transform model and route definitions into Pydantic schemas.

In Bazis, these Pydantic schemas are generated as follows:

- A route class is declared, specifying the target model
- Optionally, field restrictions can be defined
- Specific CRUD operations for the route can be optionally specified
- Input and output Pydantic schemas are generated based on the route and related model

## Features

- **Hybrid Framework**: Combines Django and FastAPI
- **JSON:API Specification**: Adheres to the JSON:API specification for building APIs
- **Class-Based Routes**: Routes are defined as class methods
- **Modular Design**: Easily extendable and customizable
- **Settings Management System**: Implementation via `django.conf.settings` with support for environment variables and admin panel
- **Automatic Schema Generation**: Pydantic schemas are automatically generated based on Django models
- **Nested Structures Support**: Thanks to JSON:API, includes support for `included`, multi-level filtering, and more
- **Dynamic Fields**: Flexible field configuration at the route level
- **High Performance**: FastAPI's asynchronous capabilities provide low latency
- **Calculated Fields**: Powerful system for working with related data via `@calc_property` decorator

## Advantages Over Other Solutions

1. **Performance**: FastAPI's asynchronous capabilities provide high performance and low latency
2. **Flexibility**: Combines the best aspects of Django and FastAPI
3. **Ease of Use**: Simplifies the development process through class-based routes and dependency injection
4. **Scalability**: Designed to handle large-scale applications
5. **Standards Compliance**: Adheres to JSON:API and OpenAPI specifications to ensure consistency and interoperability

## Requirements

- **Python**: 3.12+
- **PostgreSQL**: 12+
- **Redis**: For caching

> **Note!** The current implementation of the framework requires **Redis** as the cache backend and **PostgreSQL** as the database.

## Installation

### Using uv (recommended)

```bash
uv add bazis
```

### Using pip

```bash
pip install bazis
```

### For development

```bash
git clone git@github.com:ecofuture-tech/bazis.git
cd bazis
uv sync --dev
```

## Deployment

The backend consists of 2 services:
- API service
- Admin service

### Deployment Scripts

- `deploy/run/app_init.sh` - initialization procedures
- `deploy/run/app.sh` - start API service
- `deploy/run/admin.sh` - start admin service
- `deploy/run/tests.sh` - run tests

### Gunicorn Configs

- `deploy/config/app.py` - API service config
- `deploy/config/admin.py` - admin service config

### Environment Variables

Required environment variables:

- `BS_DEBUG` - debug mode
- `BS_DB_HOST` - database host
- `BS_DB_PORT` - database port
- `BS_DB_NAME` - database name
- `BS_DB_USER` - database user
- `BS_DB_PASSWORD` - database password
- `BS_MEDIA_ROOT` - full path to media files folder
- `BS_STATIC_ROOT` - full path to static files folder
- `BS_APP_PORT` - API service port
- `BS_ADMIN_PORT` - admin service port
- `BS_MEDIA_URL` - absolute URL for media files folder
- `BS_STATIC_URL` - absolute URL for static files folder
- `BS_ADMIN_NAME` - admin username for admin service
- `BS_ADMIN_PASSWORD` - admin password for admin service

## Auto-Documentation

### Swagger UI

Available at `/api/swagger/`

Features:
- Ability to authenticate and execute requests
  - Click the "Authorize" button
  - Enter username and password (leave other fields empty)
- List of all endpoints with schemas displayed below

### ReDoc

Available at `/api/redoc/`

Features:
- More readable endpoint documentation
- Does not allow request execution

## Usage

### Creating Models

Create models by inheriting from base classes:

```python
from bazis.core.models_abstract import InitialBase, DtMixin, UuidMixin, JsonApiMixin
from django.db import models

class VehicleBrand(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle brand."""
    name = models.CharField('Brand Name', max_length=255, unique=True)

    class Meta:
        verbose_name = 'Vehicle Brand'
        verbose_name_plural = 'Vehicle Brands'

    def __str__(self):
        return self.name
```

> **Important!** Every model and mixin must inherit from `bazis.core.models_abstract.InitialBase`.

**Example model with Foreign Key:**

```python
class VehicleModel(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle model."""
    brand = models.ForeignKey(VehicleBrand, verbose_name='Brand', on_delete=models.CASCADE)
    model = models.CharField('Model', max_length=255, unique=True)
    engine_type = models.CharField('Engine Type', max_length=50, null=True, blank=True)
    capacity = models.DecimalField(
        'Capacity, t', max_digits=6, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Vehicle Model'
        verbose_name_plural = 'Vehicle Models'
        unique_together = ('brand', 'model')

    def __str__(self):
        return self.model
```

**Example model with ManyToMany:**

```python
class Driver(DtMixin, UuidMixin, JsonApiMixin):
    """Driver."""
    first_name = models.CharField('First Name', max_length=255)
    last_name = models.CharField('Last Name', max_length=255)
    contact_phone = models.CharField('Phone', max_length=50, null=True, blank=True)

    divisions = models.ManyToManyField(
        'Division',
        related_name='drivers',
        blank=True,
    )
    org_owner = models.ForeignKey(
        'Organization',
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = 'Driver'
        verbose_name_plural = 'Drivers'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'
```

**Example model with OneToOne:**

```python
class ExtendedEntity(ExtendedEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    parent_entity = models.OneToOneField(
        'ParentEntity', on_delete=models.CASCADE, related_name='extended_entity'
    )
```

**Example model with calculated field:**

```python
from decimal import Decimal
from bazis.core.utils.orm import calc_property, FieldRelated
from bazis.core.utils.functools import get_attr

class Vehicle(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle with calculated fields."""
    vehicle_model = models.ForeignKey(
        VehicleModel, verbose_name='Vehicle Model', on_delete=models.CASCADE
    )
    country = models.ForeignKey(Country, verbose_name='Country', on_delete=models.CASCADE)
    gnum = models.CharField('State Registration Number', max_length=50, unique=True)

    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_capacity(self) -> Decimal:
        return get_attr(self, 'vehicle_model.capacity', Decimal(0.00))

    class Meta:
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'

    def __str__(self):
        return self.gnum
```

### Creating Routes

Create routes for your models:

```python
from django.apps import apps
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase

class VehicleBrandRouteSet(JsonapiRouteBase):
    """Route for VehicleBrand"""
    model = apps.get_model('entity.VehicleBrand')
```

**Route with additional fields:**

```python
from bazis.core.schemas.fields import SchemaField, SchemaFields

class ParentEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ParentEntity')

    # Add fields (extended_entity, dependent_entities and calculated properties) to schema
    fields = {
        None: SchemaFields(
            include={
                'extended_entity': None,
                'dependent_entities': None,
                'active_children': SchemaField(source='active_children', required=False),
                'count_active_children': SchemaField(
                    source='count_active_children', required=False
                ),
                'has_inactive_children': SchemaField(
                    source='has_inactive_children', required=False
                ),
                'extended_entity_price': SchemaField(
                    source='extended_entity_price', required=False
                ),
            },
        ),
    }
```

**Route with ManyToMany relationship inclusion:**

```python
class ChildEntityRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.ChildEntity')

    fields = {
        None: SchemaFields(
            include={
                'parent_entities': None,  # ManyToMany relationship
            },
        ),
    }
```

### Registering Routes

**Creating router.py in your application:**

```python
from bazis.core.routing import BazisRouter
from . import routes

# Main router with tags for grouping
router = BazisRouter(tags=['Entity'])

router.register(routes.ChildEntityRouteSet.as_router())
router.register(routes.DependentEntityRouteSet.as_router())
router.register(routes.ExtendedEntityRouteSet.as_router())
router.register(routes.ParentEntityRouteSet.as_router())
router.register(routes.VehicleModelRouteSet.as_router())
router.register(routes.VehicleBrandRouteSet.as_router())
router.register(routes.CountryRouteSet.as_router())
router.register(routes.CarrierTaskRouteSet.as_router())
router.register(routes.DivisionJsonRouteSet.as_router())
router.register(routes.DriverRouteSet.as_router())

# Create specialized routers with prefixes
router_context = BazisRouter(tags=['Context'])
router_context.register(routes.DriverContextRouteSet.as_router())

router_json = BazisRouter(tags=['Json'])
router_json.register(routes.DriverJsonHierarchyRouteSet.as_router())
router_json.register(routes.VehicleJsonRouteSet.as_router())

router_related = BazisRouter(tags=['Related'])
router_related.register(routes.VehicleRelatedRouteSet.as_router())

# Dictionary of routers with prefixes
routers_with_prefix = {
    'context': router_context,
    'json': router_json,
    'related': router_related,
}
```

**Main project router.py:**

```python
from bazis.core.routing import BazisRouter

router = BazisRouter(prefix='/api/v1')

# Register application modules
router.register('entity.router')
router.register('dynamic.router')
router.register('route_injection.router')
router.register('sparse_fieldsets.router')
```

### Project Configuration

The settings management system is implemented through `django.conf.settings`. Values can be set either via environment variables or in the admin panel.

Each Bazis application defines a `conf.py` module containing a Pydantic `Settings` schema with configuration fields.

Example `conf.py`:

```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    debug: bool = False
    secret_key: str
    database_url: str
    
    class Config:
        env_prefix = 'BS_'
```

## API Features

### Data Schema Analysis

#### OpenAPI Schema

- Primary API analysis (endpoints, attributes) can be obtained from `/api/openapi.json`
- When making requests as an authenticated user, some fields may be removed or have different access levels
- For each CRUD action, you can request the actual schema:
  - Schemas are provided in OpenAPI format
  - Available schemas:
    - `schema_list` - schema for listing items
    - `schema_create` - schema for creating items
    - `{item_id}/schema_retrieve` - schema for retrieving specific item
    - `{item_id}/schema_update` - schema for updating specific item

#### Field Attributes

- `required` - required fields
- `title` - human-readable name
- `description` - extended field description
- `nullable` - when true, field can accept "null" value
- `readOnly` - field is read-only
- `writeOnly` - field is write-only
- `enum` - list of values the field can accept
- `enumDict` - dictionary mapping values to human-readable names
- `format` - non-standard field format
- `minLength` - minimum allowed string length
- `maxLength` - maximum allowed string length
- `filterLabel` - field can be used in filtering with specified label

### Filtering

The framework provides powerful filtering capabilities through query parameters:

#### Filter Types

**Exact Match:**
```
# Single value
?filter[type]=FIRST

# Multiple values
?filter[type]=FIRST&filter[type]=SECOND
```

**Boolean Values:**
```
# False value
?filter[is_active]=false

# True value (anything except 'false')
?filter[is_active]=true
```

**Range Filters:**

Available for numeric and datetime fields with postfixes:
- `gt` - greater than
- `gte` - greater than or equal
- `lt` - less than
- `lte` - less than or equal

Examples:
```
?filter[dt_created__gte]=2022-05-16
?filter[price__lt]=5.2
```

**Nested Filters:**

For fields defined in the relationships block:
1. Determine the type of nested object
2. Find the nested object schema
3. Get fields available for filtering

Example:
```
# For organization.organization type
?filter[org_owner__tin]=7845612348
```

**Full-Text Search:**

Use the `$search` modifier for full-text search:
```
# Search in nested relationships (two levels deep)
?filter[facility_operations__fkkos__$search]=test

# Search in root results
?filter[$search]=test
```

### Included Resources (JSON:API)

Bazis implements the JSON:API specification for handling related resources through the `included` feature, allowing you to fetch related data in a single request.

### Error Format

- Expected errors return status code `422`
- Error message format follows JSON:API specification

## Examples

### Basic Route Usage

```python
from django.apps import apps
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from bazis.core.routing import BazisRouter

class VehicleRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.Vehicle')
    # All CRUD operations are available by default

router = BazisRouter(tags=['Vehicles'])
router.register(VehicleRouteSet.as_router())
```

### Limiting Fields in Routes

```python
from bazis.core.schemas.fields import SchemaFields

class VehicleRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.Vehicle')
    
    fields = {
        None: SchemaFields(
            include={
                # Specify only needed fields
                'gnum': None,
                'vehicle_model': None,
                'country': None,
            },
        ),
    }
```

### Adding Calculated Fields to API

```python
from bazis.core.schemas.fields import SchemaField, SchemaFields

class VehicleRelatedRouteSet(JsonapiRouteBase):
    model = apps.get_model('entity.Vehicle')

    fields = {
        None: SchemaFields(
            include={
                # FieldRelated - vehicle_capacity
                'vehicle_capacity_1': SchemaField(source='vehicle_capacity_1', required=False),
                'vehicle_capacity_2': SchemaField(source='vehicle_capacity_2', required=False),
                'vehicle_capacity_3': SchemaField(source='vehicle_capacity_3', required=False),
                # FieldRelated - brand, multiple fields
                'brand_info': SchemaField(source='brand_info', required=False),
                # FieldRelated - brand and country
                'brand_and_country': SchemaField(source='brand_and_country', required=False),
            },
        ),
    }
```

### Working with Admin Panel

```python
from django.contrib import admin
from bazis.core.admin_abstract import DtAdminMixin

@admin.register(VehicleBrand)
class VehicleBrandAdmin(DtAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)
```

**Admin with inline models:**

```python
class ChildEntityInline(admin.TabularInline):
    model = ParentEntity.child_entities.through
    extra = 0

class DependentEntityInline(admin.TabularInline):
    model = DependentEntity
    extra = 0

@admin.register(ParentEntity)
class ParentEntityAdmin(DtAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    inlines = (ChildEntityInline, DependentEntityInline)
```

## Architecture

### Package Structure

The **bazis** package is the core project installed under the `bazis.core` namespace.
Extension packages are installed under the `bazis.contrib` namespace.

### Application Structure

All files are optional:

```
app/
├── models_abstract.py      # Mixins or abstractions for creating models
├── admin_abstract.py       # Mixins for creating admin classes
├── routes_abstract.py      # Mixins and base classes for routes
├── models.py               # Actual application models
├── admin.py                # Admin classes
├── routes.py               # Route classes
├── router.py               # URL routing
├── schemas.py              # Static Pydantic schemas
├── triggers.py             # Django-pgtrigger triggers
└── services/
    └── services.py         # Dependency services
```

### Bazis Models Features

- Every model and mixin must inherit from `bazis.core.models_abstract.InitialBase`
- The logic of missing Meta class in a model has been changed:
  - By default in Django, if a model does not define a Meta class, Meta parameters are considered unset
  - Bazis adds default inheritance functionality from all parent classes, meaning if the Meta class is not defined, the model will receive a composite Meta class from all parents in the order of model inheritance

### Dynamic Fields

Bazis supports dynamic fields that can be configured at the route level for greater flexibility.

### JSON:API

The framework uses the JSON:API specification, which includes:
- Support for nested structures via `included`
- Multi-level filtering
- Standardized response format
- Relationships between resources

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone git@github.com:ecofuture-tech/bazis.git
cd bazis

# Install dependencies
uv sync --dev

# Run tests (from sample directory)
cd sample
pytest ../tests

# Check code
ruff check .

# Format code
ruff format .
```

## Contributing

Contributions are welcome! Here's how you can help:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`cd sample && pytest ../tests`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

Please make sure to:
- Write tests for new features
- Update documentation as needed
- Follow the existing code style
- Add your changes to the changelog

## License

Apache License 2.0

See [LICENSE](LICENSE) file for details.

## Links

- [Bazis Documentation](https://github.com/ecofuture-tech/bazis) — main repository
- [Issue Tracker](https://github.com/ecofuture-tech/bazis/issues) — report bugs or request features
- [Bazis Test Utils](https://github.com/ecofuture-tech/bazis-test-utils) — testing utilities

## Support

If you have questions or issues:
- Check the [documentation](https://github.com/ecofuture-tech/bazis)
- Search [existing issues](https://github.com/ecofuture-tech/bazis/issues)
- Create a [new issue](https://github.com/ecofuture-tech/bazis/issues/new) with detailed information

## Ecosystem Packages

Bazis supports extensions through additional packages:

- `bazis-test-utils` — testing utilities
- `bazis-<n>` — other extensions (add `bazis-` prefix to the name)

All extension packages require the `bazis` core package to be installed.

---

Made with ❤️ by the Bazis team