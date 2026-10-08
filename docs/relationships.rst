Relationships
=============

The JSON:API relationship management functionality is implemented in the ``RelationshipsService`` and allows
managing relationships between model objects through standard HTTP requests to endpoints in JSON:API format.
https://jsonapi.org/format/#crud-updating-relationships

All types of relationships are supported:

* **M2M** — many-to-many
* **O2M / M2O** — one-to-many / many-to-one (FK)
* **O2O** — one-to-one

General features

* **Response codes:** All operations return ``204 No Content`` on successful execution
* **Data format:** Strictly complies with JSON:API specification
* **Relationship types:** Determined automatically based on Django models
* **Transactionality:** All operations are executed within transactions
* **Validation:** Object existence and type correctness are verified

Access to the related objects
-----------------------------

The default route of a model (``Model.get_default_route()``) defines which of its objects
the other routes can link and include: the classmethod ``restrict_queryset`` of
``RestrictedQsRouteMixin``. The core calls it with ``user`` (the user of the request,
``None`` without bazis-users) and ``route`` (the route of the request); an override accepts
``**kwargs``.

.. code-block:: python

    class TagRouteSet(RestrictedQsRouteMixin):
        model = apps.get_model('notes.Tag')
        default_route = True

        @classmethod
        def restrict_queryset(cls, qs, access_action, user=None, **kwargs):
            qs = qs.filter(is_hidden=False)
            if access_action == CrudAccessAction.CHANGE:
                qs = qs.filter(is_locked=False)
            return qs

        def get_queryset(self):
            # the list and the item of the route itself
            return self.restrict_queryset(super().get_queryset(), CrudAccessAction.VIEW)

* A created or changed item (create, update, the relationships endpoints above) links only
  the objects ``restrict_queryset`` returns for ``view``; a reverse relationship changes the
  foreign key of the objects it links and unlinks, so they must be returned for ``change``.
  Only the objects whose link changes are checked: an object linked before stays linked
  and can be unlinked. Otherwise the request fails with ``403``, code
  ``ERR_RELATION_ACCESS`` and the pointer ``/data/relationships/<field>``.
* ``included`` contains only the objects ``restrict_queryset`` returns for ``view``; the
  relationship keeps the identifiers of all linked objects.
* The objects of a model whose default route does not override ``restrict_queryset``, or
  that has no route, are not checked (no extra query).
* ``relations_view_check = False`` on a route turns the check of its relationships off.
* The default route of a model is the last defined route class of the model (abstract ones
  never), unless a route class declares ``default_route = True`` in its body (the flag is
  not inherited). ``bazis_doctor`` warns (``bazis.W003``) about a model with several route
  sets and not one explicit default route.

M2M (Many-to-Many)
------------------

### Adding relationships (POST)

**Result:** Existing relationships are preserved, new relationships with specified child objects are added.

**From parent side (add children to parent):**

.. code-block:: bash

    curl -X 'POST' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/child_entities' \
      -d '{
        "data": [
          { "type": "entity.child_entity", "id": "4a4bf25b-7617-456b-9863-fb761fb70983" },
          { "type": "entity.child_entity", "id": "fd2db2ac-25a1-4c70-8955-0f3fb1096cba" }
        ]
      }'

**From child side (add parents to child):**

.. code-block:: bash

    curl -X 'POST' \
      '/api/v1/entity/child_entity/{child_id}/relationships/parent_entities' \
      -d '{
        "data": [
          { "type": "entity.parent_entity", "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" },
          { "type": "entity.parent_entity", "id": "a1b2c3d4-5717-4562-b3fc-2c963f66afa6" }
        ]
      }'

### Replacing relationships (PATCH)

**Result:** All previous relationships are removed, only specified relationships are established.

**From parent side (complete replacement of all children):**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/child_entities' \
      -d '{
        "data": [
          { "type": "entity.child_entity", "id": "4a4bf25b-7617-456b-9863-fb761fb70983" },
          { "type": "entity.child_entity", "id": "fd2db2ac-25a1-4c70-8955-0f3fb1096cba" }
        ]
      }'

**From child side (complete replacement of all parents):**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/child_entity/{child_id}/relationships/parent_entities' \
      -d '{
        "data": [
          { "type": "entity.parent_entity", "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
        ]
      }'

**Clearing all relationships:**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/child_entities' \
      -d '{
        "data": []
      }'

### Deleting relationships (DELETE)

**Result:** Only specified relationships are removed, others are preserved.

**From parent side (remove specific children):**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/child_entities' \
      -d '{
        "data": [
          { "type": "entity.child_entity", "id": "4a4bf25b-7617-456b-9863-fb761fb70983" }
        ]
      }'

**From child side (remove specific parents):**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/child_entity/{child_id}/relationships/parent_entities' \
      -d '{
        "data": [
          { "type": "entity.parent_entity", "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
        ]
      }'

O2O (One-to-One)
----------------

### Setting relationship (POST/PATCH)

**O2O specifics:**
- For O2O relationships POST and PATCH work identically - they establish the relationship
- When setting a new relationship, the old one is broken if possible
- Data is passed as an object, not an array

**From parent side:**

.. code-block:: bash

    # POST or PATCH - work the same for adding/replacing one relationship in O2O
    curl -X 'POST' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/extended_entity_null' \
      -d '{
        "data": {
          "type": "entity.extended_entity_null",
          "id": "08b95853-42ea-49e3-ba7b-e5d004a16bb9"
        }
      }'

**From extended side:**

.. code-block:: bash

    curl -X 'POST' \
      '/api/v1/entity/extended_entity_null/{extended_id}/relationships/parent_entity' \
      -d '{
        "data": {
          "type": "entity.parent_entity",
          "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        }
      }'

**Clearing relationship with PATCH:**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/extended_entity_null/{extended_id}/relationships/parent_entity' \
      -d '{
        "data": null
      }'

### Deleting relationship (DELETE)

**From parent side:**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/extended_entity_null' \
      -d '{
        "data": {
          "type": "entity.extended_entity_null",
          "id": "08b95853-42ea-49e3-ba7b-e5d004a16bb9"
        }
      }'

**From extended side:**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/extended_entity_null/{extended_id}/relationships/parent_entity' \
      -d '{
        "data": {
          "type": "entity.parent_entity",
          "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        }
      }'

O2M / M2O (Foreign Key)
----------------------------

### Adding relationships (POST)

**Result:** Dependent entities have their foreign key set to the parent.

**From parent side:**

.. code-block:: bash

    curl -X 'POST' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/dependent_entities_null' \
      -d '{
        "data": [
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f55"},
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f59"}
        ]
      }'

**From dependent side:**

.. code-block:: bash

    curl -X 'POST' \
      '/api/v1/entity/dependent_entity_null/{depend_id}/relationships/parent_entity' \
      -d '{
        "data": {"type": "entity.parent_entity", "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}
      }'

### Replacing relationships (PATCH)

**Result:** Complete replacement of dependent entities. Previous dependent entities have their foreign key reset (becomes NULL), new ones have it set.

**From parent side:**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/dependent_entities_null' \
      -d '{
        "data": [
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f55"},
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f59"}
        ]
      }'

**From dependent side:**

.. code-block:: bash

    curl -X 'PATCH' \
      '/api/v1/entity/dependent_entity_null/{depend_id}/relationships/parent_entity' \
      -d '{
        "data": {"type": "entity.parent_entity", "id": "new-parent-id-here"}
      }'

### Deleting relationships (DELETE)

**Result:** Set foreign key to NULL for specific dependent entities.

**From parent side:**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/parent_entity/{parent_id}/relationships/dependent_entities_null' \
      -d '{
        "data": [
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f55"},
          {"type": "entity.dependent_entity_null", "id": "38778e0a-d30c-4408-90aa-a47693f54f59"}
        ]
      }'

**From dependent side:**

.. code-block:: bash

    curl -X 'DELETE' \
      '/api/v1/entity/dependent_entity_null/{depend_id}/relationships/parent_entity' \
      -d '{
        "data": {"type": "entity.parent_entity", "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}
      }'