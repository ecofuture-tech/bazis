OpenAPI Schemas
===============

The JsonAPI standard defines the structure of an object as follows:

- **id**: unique identifier of the object in the system.
- **type**: unified object type.
- **attributes**: set of simple attributes.
- **relationships**: attributes linking to external objects.

**Bazis Implementation Features**

In addition to the main fields mentioned above, an additional field **bs:action** is added. It takes values of actions that affect the object (view, change, add), described in the section :ref:`object-actions`. This field is especially useful for included objects to be able to add or change them independently of the action type on the main object.

**OpenAPI Schema Extension for Attributes**

Inside the OpenAPI schema for attributes of type *attributes*, the following characteristics are added:

- **orderLabel**: if filled, this attribute can be used with the specified label as a sorting *sort* parameter.
  - Labels are listed separated by commas, for reverse sorting, specify "-" before the label.
- **filterLabel**: if filled, this attribute can be used with the specified label as a filtering *filter* parameter.
  - Filtering operations are described below.

Working with Filters
--------------------

The JsonAPI protocol prescribes setting list filters in the GET parameter *filter*.
The set of filters is a URL-encoded string. The filter parameter keys are field labels of the *filterLabel* schema.

Filter string format - extended query string:

- "AND" operation: ``&``
- "OR" operation: ``|``
- Negation: prefixed by ``~``
- Grouping operation is enclosed in parentheses: ``()``

**Important**: When adding this string to the URL request in the *filter* parameter, it must be URL-encoded.

**Example of Filtering**

Assume an entity has fields: *name* [str], *price* [int], *status* [str]. You need to create a filter string where "name equals test" and "price equals 100 or 200" and "status does not equal progress". The filter string will look like this:
``name=test&(price=100|price=200)&~status=progress``. The full URL will look like this:
``https://domain.com/api/web/v1/app/entity/?filter=name%3Dtest%26%28price%3D100%7Cprice%3D200%29%26~status%3Dprogress``

Filtering implementation in Bazis: :py:mod:`~bazis.core.services.filtering`

**Supported Operations in Filters**

- **For boolean fields**: values *false*, *0*. For example, ``is_validate=false``.
- **For geo-point fields**:
  - Match to within 10m: ``point=49.124,55.76480``.
  - Match with specified accuracy in meters: ``point__near=49.124,55.76480,100``, where the last parameter is the accuracy in meters.
  - Fall within specified bbox: ``point__in_bbox=160.6,-55.95,-170,-25.89``.
- **For array fields**: match one of several values. Values are listed separated by commas. For example, ``types=type1,type2,type3``.
- **For text fields (TextField)**: substring search.
- **For other fields**: exact match search.
- **For explicit null value search**: special postfix ``__isnull``. For example, ``point__isnull=true`` for the *point* field.
- **For numeric fields**: comparison operations *'gt'*, *'gte'*, *'lt'*, *'lte'*. For example, ``number__gte=5``.

Full-Text Search in Filtering
------------------------------

- ``$search=text``: Identical to the top-level query ``'?search=text'``. Full-text search across all text and integer fields of the model.
- ``description__$search=some text``: Full-text search only in the *description* text field.
- ``author__$search=text``: Full-text search across all text and integer fields of the nested *author* model.
- ``author__username__$search=text``: Full-text search only in the *username* text field of the nested *author* entity.

Working with Related Entities
-----------------------------

A related entity is available in the **relationships** block in the OpenAPI schema. Based on the related entity type, you can find definitions of its fields in the OpenAPI schema and filter by them. Access to the internal fields of a related entity is through a double underscore: ``__``. For example, ``facility__point=49.124,55.76480``.

A special filter for checking the existence of a related object is available through the postfix ``__exists``:
For example, to check if there is a related *facility* object in the current object, you can use: ``facility__exists=true``.
