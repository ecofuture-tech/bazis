import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db()
def test_filter_fields_calc_bool(sample_app):
    """
    Calculated field with Bool response.

    Calculated field for vehicles (Vehicle model) with information about whether the car
    has an active trip (CarrierTask model).

    .. code-block:: python

        @calc_property(
            [
                FieldIsExists(
                    source='carrier_tasks',
                    query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
                    alias='has_active_trip',
                ),
            ],
            as_filter=True
        )
        def has_active_trip(self) -> bool:
            return get_attr(self, 'has_active_trip', False)
    """

    url = '/api/v1/has_active_trip/entity/vehicle/route_filter_fields/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/entity/vehicle_model/'},
            {'name': 'country', 'py_type': '/api/v1/entity/country/'},
            {'name': 'has_active_trip', 'py_type': 'boolean'},
        ]
    }
