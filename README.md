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

class Article(InitialBase):
    title = models.CharField(max_length=255)
    content = models.TextField()

# Create a route
from bazis.core.routes_abstract import BaseRoute

class ArticleRoute(BaseRoute):
    model = Article
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
  - [Project Configuration](#project-configuration)
- [API Features](#api-features)
  - [Data Schema Analysis](#data-schema-analysis)
  - [Filtering](#filtering)
  - [Included Resources](#included-resources-jsonapi)
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
from bazis.core.models_abstract import InitialBase
from django.db import models

class Article(InitialBase):
    """Article model"""
    title = models.CharField(max_length=255, verbose_name="Title")
    content = models.TextField(verbose_name="Content")
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="Publication Date")
    
    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
```

> **Important!** Every model and mixin must inherit from `bazis.core.models_abstract.InitialBase`.

### Creating Routes

Create routes for your models:

```python
from bazis.core.routes_abstract import BaseRoute
from .models import Article

class ArticleRoute(BaseRoute):
    """Route for working with articles"""
    model = Article
    
    # Optionally: specify specific CRUD operations
    # allowed_methods = ['list', 'retrieve', 'create', 'update', 'delete']
```

Register routes in `router.py`:

```python
from bazis.core.router import Router
from .routes import ArticleRoute

router = Router()
router.register(ArticleRoute)
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
from bazis.core.routes_abstract import BaseRoute
from bazis.core.router import Router
from .models import Article

class ArticleRoute(BaseRoute):
    model = Article
    # All CRUD operations are available by default

router = Router()
router.register(ArticleRoute)
```

### Limiting Fields in Routes

```python
class ArticleRoute(BaseRoute):
    model = Article
    
    # Read fields
    read_fields = ['id', 'title', 'content', 'published_at']
    
    # Create fields
    create_fields = ['title', 'content']
    
    # Update fields
    update_fields = ['title', 'content', 'published_at']
```

### Specifying Specific Operations

```python
class ArticleRoute(BaseRoute):
    model = Article
    
    # Read-only (list and retrieve)
    allowed_methods = ['list', 'retrieve']
```

### Using Relationships

```python
from django.db import models

class Author(InitialBase):
    name = models.CharField(max_length=255)

class Article(InitialBase):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='articles')

# JSON:API will automatically handle relationships
class ArticleRoute(BaseRoute):
    model = Article
    read_fields = ['id', 'title', 'author']  # author will be in relationships
```

### Working with Admin Panel

```python
from django.contrib import admin
from bazis.core.admin_abstract import BaseAdmin
from .models import Article

@admin.register(Article)
class ArticleAdmin(BaseAdmin):
    list_display = ['id', 'title', 'published_at']
    search_fields = ['title', 'content']
    list_filter = ['published_at']
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