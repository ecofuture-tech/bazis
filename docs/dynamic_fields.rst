Dynamic fields
==============


``FieldDynamic`` is a declarative builder for computed fields, used through the ``@calc_property`` decorator.

When calling ``FieldDynamic()``, it automatically transforms into one of the ``Field*`` classes:

- ``FieldIsExists`` (boolean indicator for a specified combination of conditions) — if ``alias`` starts with ``has_``.
- ``FieldSubAggr`` (aggregation result) — if ``func`` is specified.
- ``FieldJson`` (list of values for one-to-many and many-to-many relationships) — if ``fields`` are defined.
- ``FieldRelated`` (values for one-to-one and many-to-one relationships) — in all other cases.

``DependsCalc`` is a helper mechanism for passing dependencies.
It creates a Pydantic model from fields specified in ``FieldDynamic``, taking nesting into account.
Used in ``@calc_property`` to pass dependency values to methods.



One to many
-----------
A computed field can return a list of values from related "one to many" tables.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_json__one_to_many
   :members:
   :member-order: bysource


Many to many
------------
A computed field can return a list of values from related "many to many" tables.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_json_many_to_many
   :members:
   :member-order: bysource


Many to one
-----------
A computed field can return values from related "many to one" tables.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_related__many_to_one
   :members:
   :member-order: bysource


One to one
----------
A computed field can return values from related "one to one" tables.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_related__one_to_one
   :members:
   :member-order: bysource


Boolean
-------
A computed field can return a boolean indicator of whether a combination of conditions is met.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_related_bool
   :members:
   :member-order: bysource


Aggregation
-----------
A computed field can return aggregations from related tables.

.. automodule:: tests.test_routes_view.dynamic.field_types.test_subaggr
   :members:
   :member-order: bysource


Context
-------
Through context and query, you can configure automatic filtering of data retrieved from related tables.

.. automodule:: tests.test_routes_view.dynamic.test_context
   :members:
   :member-order: bysource