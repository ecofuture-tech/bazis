Sparse Fieldsets
================

The JSON:API functionality for limiting the list of returned fields allows passing a list of fields through the query parameter fields[TYPE].

.. code-block:: text

    ?fields[<resource_type>]=<field1>,<field2>,...

https://jsonapi.org/format/#fetching-sparse-fieldsets

Limiting fields when retrieving a list
---------------------------------------

   Request:

   .. code-block:: text

      GET /api/v1/sparse_fieldsets/article/?fields[sparse_fieldsets.article]=title,author_count

   The response will contain only the specified fields, including computed ones. If relationship fields were not specified, relationships will be empty.

   .. code-block:: json

      {
          "data": [{
              "attributes": {
                  "title": "somestring 1",
                  "author_count": 1
              },
              "bs:action": "view",
              "id": "1",
              "relationships": {},
              "type": "sparse_fieldsets.article"
          }],
          "links": {...},
          "meta": {}
      }

Limiting fields when retrieving an object
------------------------------------------

   Request:

   .. code-block:: text

      GET /api/v1/sparse_fieldsets/article/1/?fields[sparse_fieldsets.article]=title,dt_created,author_count

   Response:

   .. code-block:: json

      {
          "data": {
              "attributes": {
                  "author_count": 1,
                  "dt_created": "2023-01-01T12:00:00",
                  "title": "somestring 1"
              },
              "bs:action": "view",
              "id": "1",
              "relationships": {},
              "type": "sparse_fieldsets.article"
          },
          "meta": {}
      }

Limiting fields of related models
----------------------------------

   Request:

   .. code-block:: text

      GET /api/v1/sparse_fieldsets/article/1/?fields[sparse_fieldsets.article]=title&include=author&fields[sparse_fieldsets.people]=name,email

   Response:

   .. code-block:: json

      {
          "data": {
              "attributes": {"title": "somestring 1"},
              "bs:action": "view",
              "id": "1",
              "relationships": {},
              "type": "sparse_fieldsets.article"
          },
          "included": [{
              "attributes": {
                  "email": "somestring 2",
                  "name": "somestring 3"
              },
              "bs:action": "view",
              "id": "1",
              "relationships": {},
              "type": "sparse_fieldsets.people"
          }],
          "meta": {}
      }

Limiting fields of multiple related models
-------------------------------------------

   Request:

   .. code-block:: text

      GET /api/v1/sparse_fieldsets/article/1/?fields[sparse_fieldsets.article]=title&include=author,category&fields[sparse_fieldsets.people]=name&fields[sparse_fieldsets.category]=name

   Response:

   .. code-block:: json

      {
          "data": {
              "attributes": {"title": "somestring 1"},
              "bs:action": "view",
              "id": "1",
              "relationships": {},
              "type": "sparse_fieldsets.article"
          },
          "included": [
              {
                  "attributes": {"name": "somestring 2"},
                  "bs:action": "view",
                  "id": "1",
                  "relationships": {},
                  "type": "sparse_fieldsets.people"
              },
              {
                  "attributes": {"name": "somestring 3"},
                  "bs:action": "view",
                  "id": "1",
                  "relationships": {},
                  "type": "sparse_fieldsets.category"
              }
          ],
          "meta": {}
      }