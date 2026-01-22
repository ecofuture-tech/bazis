Routing
=======

Routing in the framework takes a special place.
It was developed with several features in mind:

- **Class-Oriented Route**: Abstract route classes can be defined, which determine generalized functionality, and the final route can inherit from several such classes.
- **Based on FastAPI logic**
- **CRUD functionality for Django models**: should be connected by default, without the need to explicitly list fields, operations, etc. Based on the attribute composition of models, Pydantic schemas will be generated.

Class routes are useful for combining method routes of a single entity, for example, for one Django model.

The base route class is :py:class:`~bazis.core.routes_abstract.initial.InitialRouteBase`.
It allows implementing class-oriented routes.

**Lifecycle of InitialRouteBase class and its objects**:

When defining a specific class, the meta-class :py:class:`~bazis.core.routes_abstract.initial.InitialRouteBaseMeta`:
  - Collects Inject classes from the class inheritance tree and creates a combined InjectCommon class,
    including dependencies from all parent classes with tags.
  - Collects the attribute :py:attr:`~bazis.core.routes_abstract.initial.InitialRouteBase.routes_ctx`, containing route wrapper objects for the current class.
  - Calls the initializing method :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.cls_init`, which can be overridden for child classes.

An object of the :py:class:`~bazis.core.routes_abstract.initial.InitialRouteBase` class is created when FastAPI receives a request and calls a specific route.

**Setting the class as a router**:

To do this, call the :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.as_router` method of the class. It creates a private router and initiates the creation of an endpoint function and its registration for each route context.

.. note::
    The creation of the endpoint function is performed by the :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.endpoint_make` method. This method creates the final Inject class for initializing dependencies, considering the dependencies defined in the function signature.
    Then, an endpoint function is created, which receives the signature of the original function. A dependency is added to it, which creates the object and sets it as the ``self`` parameter in the endpoint function signature.
    The endpoint function calls the :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.route_run` function, which in turn calls the original function.
    If necessary, in inherited classes, the :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.route_run` can define logic common to all routes of the class.
    The endpoint registration occurs in the :py:meth:`~bazis.core.routes_abstract.initial.InitialRouteBase.endpoint_register` method, and it sets the endpoint in the specified FastAPI router.

**Main features of the :py:class:`~bazis.core.routes_abstract.initial.InitialRouteBase` class**:

**Route Methods**

Within a class route, you need to define one or more route methods. They are defined using decorators:

- :py:func:`~bazis.core.routes_abstract.initial.http_get`
- :py:func:`~bazis.core.routes_abstract.initial.http_put`
- :py:func:`~bazis.core.routes_abstract.initial.http_post`
- :py:func:`~bazis.core.routes_abstract.initial.http_patch`
- :py:func:`~bazis.core.routes_abstract.initial.http_delete`
- :py:func:`~bazis.core.routes_abstract.initial.http_options`
- :py:func:`~bazis.core.routes_abstract.initial.http_head`
- :py:func:`~bazis.core.routes_abstract.initial.http_trace`
- :py:func:`~bazis.core.routes_abstract.initial.http_internal` (special decorator for programmatic route calls)

.. tip::
   Each decorator represents a specific HTTP method. They return an object of the :py:class:`~bazis.core.routes_abstract.initial.RouteContext` class, described below.

**RouteContext**

An object of this class is the result of decorating a class route method. It holds references to the original method, routing parameters, endpoint function, and the route's local storage.

In each class, there is a class variable :py:attr:`~bazis.core.routes_abstract.initial.InitialRouteBase.routes_ctx`, which contains :py:class:`~bazis.core.routes_abstract.initial.RouteContext` objects (equal to the number of route methods) for the current class. These objects are unique for each class (even if classes are inherited). Within each route object during request processing, the specific :py:class:`~bazis.core.routes_abstract.initial.RouteContext` will be available through ``self.route_ctx``.

**Decorator Parameters**:

- ``path``: Contains the route path relative to the class route path.
- ``cls``: If the decorator is applied to a method, specifying it is not necessary. If the route is defined by directly calling the decorator as a function, the associated class route can be explicitly passed to ``cls``.
- ``endpoint_callbacks``: List of functions that will be applied to the :py:class:`~bazis.core.routes_abstract.initial.RouteContext` object during route initialization. Function signature: ``(cls=cls, route_ctx=route_ctx)``.
- ``inject_tags``: List of tags based on which corresponding Injects will be applied to the route.
- The remaining parameters are identical to the route parameters in FastAPI.

**Injects**:

In FastAPI, there is the concept of ``Depends``. Injects are a declarative way to add Depends at the class level. Injects are classes decorated with :py:func:`~bazis.core.routes_abstract.initial.inject_make`.
The :py:func:`~bazis.core.routes_abstract.initial.inject_make` method accepts tags as attributes, with which it will be associated. If the same tags are specified in a specific route, then the Depends from the corresponding Inject will be applied to that route. In the route class, several Inject classes with different sets of Depends can be specified.

Within a route, the filled Inject will be available in the ``self.inject`` variable.

JsonapiRouteBase
----------------

In most working projects, there is no need to explicitly use ``InitialRouteBase``. To create an API that is fundamentally based on CRUD operations and Django models, it is convenient to use the route class :py:class:`~bazis.core.routes_abstract.jsonapi.JsonapiRouteBase`. This class can work with Django models by default, parsing the structure of the fields of these models and creating `JsonAPI <https://jsonapi.org/format/1.0/>`_ compatible APIs based on them.

**Key Entities within the JsonapiRouteBase Logic**

.. _object-actions:

Actions
~~~~~~~

There are two types of entity actions:

1. CRUD-like actions (list, retrieve, create, update, destroy)
2. Object-level impact actions (view, change, add, delete)

CRUD-like actions are represented by the basic structure :py:class:`~bazis.core.schemas.ApiAction`.
The standard set is defined as :py:class:`~bazis.core.schemas.CrudApiAction`. If necessary, you can create your own extended set of actions by inheriting from ``ApiAction``.

Object-level impact actions are represented by the basic structure :py:class:`~bazis.core.schemas.AccessAction`.
The standard set is defined as :py:class:`~bazis.core.schemas.CrudAccessAction`. If necessary, you can create your own extended set of actions by inheriting from ``AccessAction``.

**Routing Schemas**

When registering a class route based on ``JsonapiRouteBase``, dynamic Pydantic schemas will be created based on the original model and custom route class settings. These Pydantic schemas are default for the route class and are not recalculated further. In ``JsonapiRouteBase``, the ``endpoint_callbacks`` parameter in ``@http_...`` decorators is responsible for integrating schemas into routes. In particular, the functions ``api_action_init`` and ``api_action_response_init`` are injected into the ``endpoint_callbacks`` function list, which collect the schema for incoming and outgoing data, respectively. The assembly occurs for each ``ApiAction`` separately.

**Internal Logic of JsonAPI Pydantic Schema Assembly**

The implementation is in the :py:mod:`~bazis.core.schemas` module. The basic structure of schema assembly is :py:class:`~bazis.core.schemas.SchemaFactory`. An object of this class is created once for each ``ApiAction`` and carries default information about all available fields of the route, metadata, and accompanying objects (inclusions).

The schema assembly itself is handled by the :py:class:`~bazis.core.schemas.SchemaBuilder` class, specifically its ``build`` method. This class object is not created directly. This is handled by the :py:meth:`~bazis.core.schemas.SchemaFactory.build_schema` method.

**Route Field Configuration**

To define a custom set of route fields, use the ``bazis.core.schemas.SchemaFields`` object.
A dictionary of the form ``dict[ApiAction, SchemaFields]`` is set in the target class's ``fields`` attribute.
``SchemaFields`` contains the custom configuration of fields for a specific API action. This attribute's feature is that it does not override parent class attributes by default, allowing for very flexible route field configuration.

**SchemaFields Class Attributes**

Attributes for configuring fields in ``SchemaFields`` include:

- ``origin`` [dict]: If set, the specified dictionary of fields becomes the initial one for the route, resetting all previously set fields in parent route classes.
- ``include`` [dict]: If set, the specified dictionary of fields will complement the previously collected fields.
- ``exclude`` [dict]: If set, the dictionary of fields will exclude the specified fields from the previously collected fields.
- ``is_inherit`` [bool]: If False, parent ``fields`` attributes are ignored.

Each of these attributes is a dictionary where the key is the field label and the value is an object of the :py:class:`~bazis.core.schemas.SchemaField` class. The preferred way to specify custom fields is to work with model fields, both regular and computed (property). For this, it is sufficient to use the field name from the model as the key. However, in ``SchemaField``, there is a ``source`` attribute that allows explicitly specifying the field value source. Other attributes are described in :py:class:`~bazis.core.schemas.SchemaField`.

**Included Objects**

Within the Json-API specification, *included* is a list of additional objects that can be formed in addition to the main object. It is formed by an explicit request from the frontend and includes full-fledged objects as if they were requested separately. By default, all variations of *included* are available for the route, but their availability and composition can be customized.

To define a custom set of included objects, use the ``bazis.core.schemas.SchemaInclusions`` object.
A dictionary of the form ``dict[ApiAction, SchemaInclusions]`` is set in the target class's ``inclusions`` attribute.
``SchemaInclusions`` is similar to ``SchemaFields`` in terms of inheritance logic.

The attribute dictionaries of ``SchemaInclusions`` contain :py:class:`~bazis.core.schemas.SchemaInclusion` objects.

- ``fields_struct``: An object of type :py:class:`~bazis.core.schemas.SchemaFields`, in which the field structure can be described.
- ``meta_fields_struct``: An object of type :py:class:`~bazis.core.schemas.SchemaMetaFields`, in which the meta-field structure can be described.

``SchemaMetaFields`` is similar to ``SchemaFields``, except that the field class is ``SchemaMetaField`` - a simplified version of ``SchemaField``.

**Defining a Route Class Based on JsonapiRouteBase**

To define a route class based on ``JsonapiRouteBase``, you need to specify the following parameters:

- ``model``: The Django model that will be the basis of the endpoint set.
- ``fields``: A dictionary of ``bazis.core.schemas.SchemaFields`` objects. If not set, all explicit model fields will be used.
- ``inclusions``: A dictionary of ``bazis.core.schemas.SchemaFields`` objects. If not set, all relation fields will be available for request as included.
- ``meta_fields``: A dictionary of ``bazis.core.schemas.SchemaMetaFields`` objects. If not set, all declared metadata in the route will be available.
- ``search_fields``: A list of fields in the related model for full-text search. If not set, all string fields of the model will be used.
