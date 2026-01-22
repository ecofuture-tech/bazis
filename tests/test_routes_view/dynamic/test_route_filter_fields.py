import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.django_db()
def test_filter_fields_calc_bool(sample_app):
    """
    Calculated field with Bool response.

    Calculated field for vehicles (Vehicle model) with information about whether the vehicle
    has an active trip (CarrierTask model).

    .. code-block:: python

        @calc_property(
            [
                FieldDynamic(
                    'carrier_tasks',
                    query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
                    alias='has_active_trip',
                ),
            ],
            as_filter=True,
        )
        def has_active_trip(self, dc: DependsCalc) -> bool:
            return dc.data.has_active_trip
    """

    url = '/api/v1/is_exists_one_relation/dynamic/vehicle/route_filter_fields/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/dynamic/vehicle_model/'},
            {'name': 'has_active_trip', 'py_type': 'boolean'},
        ]
    }


@pytest.mark.django_db()
def test_filter_fields_calc_decimal(sample_app):
    """
    Calculated field with Decimal response.

    Calculated field for a vehicle (Vehicle model) with information about the load capacity of the corresponding model
    (VehicleModel model).

    .. code-block:: python

        @calc_property([FieldDynamic('vehicle_model')], as_filter=True)
        def vehicle_capacity(self, dc: DependsCalc) -> Decimal:
            return dc.data.vehicle_model.capacity
    """

    url = '/api/v1/related_one_relation_one_field/dynamic/vehicle/route_filter_fields/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/dynamic/vehicle_model/'},
            {'name': 'vehicle_capacity', 'py_type': 'Decimal'},
        ]
    }


@pytest.mark.django_db()
def test_filter_fields_calc_dict(sample_app):
    """
    Calculated field with dict response.

    Calculated field for a vehicle (Vehicle model) with factory assembly data (VehicleAssembleInfo model).

    .. code-block:: python

        @calc_property([FieldDynamic('assemble_info')], as_filter=True)
        def vehicle_assemble_info(self, dc: DependsCalc) -> dict[str, Any]:
            return {
                'assembly_date': dc.data.assemble_info.assembly_date,
                'assembly_plant': dc.data.assemble_info.assembly_plant,
            }
    """

    url = '/api/v1/related_one_to_one/dynamic/vehicle/route_filter_fields/'
    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/dynamic/vehicle_model/'},
            {'name': 'vehicle_assemble_info', 'py_type': 'object'},
        ]
    }


@pytest.mark.django_db()
def test_filter_fields_calc_list(sample_app):
    """
    Calculated field with list response.

    Calculated field for vehicles (Vehicle model) with a list of trips (CarrierTask model).

    .. code-block:: python

        @calc_property(
            [
                FieldDynamic(
                    source='carrier_tasks',
                    fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'driver_id'],
                ),
            ],
            as_filter=True,
        )
        def carrier_task_list(self, dc: DependsCalc) -> list:
            return [
                {
                    'id': task.id,
                    'dt_start': task.dt_start,
                    'dt_finish': task.dt_finish,
                    'fact_waste_weight': task.fact_waste_weight,
                    'driver_id': task.driver_id,
                }
                for task in dc.data.carrier_tasks
            ]
    """

    url = '/api/v1/json_one_relation/dynamic/vehicle/route_filter_fields/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/dynamic/vehicle_model/'},
            {'name': 'carrier_task_list', 'py_type': 'array'},
        ]
    }


@pytest.mark.django_db()
def test_filter_fields_calc_anyof(sample_app):
    """
    Calculated field with anyOf response.

    Calculated field for a vehicle (Vehicle model) that sums the weight of all transported cargo (CarrierTask model).

    .. code-block:: python

        @calc_property(
            [
                FieldDynamic(
                    source='carrier_tasks__fact_waste_weight',
                    func='Sum',
                    alias='finished_tasks_waste_weight',
                    query=Q(dt_finish__isnull=False),
                ),
            ]
            , as_filter=True
        )
        def finished_tasks_waste_weight(self, dc: DependsCalc) -> Decimal | None:
            return dc.data.finished_tasks_waste_weight
    """

    url = '/api/v1/subaggr/dynamic/vehicle/route_filter_fields/'

    response = get_api_client(sample_app).get(url)

    assert response.status_code == 200

    assert response.json() == {
        'fields': [
            {'name': 'dt_created', 'py_type': 'datetime'},
            {'name': 'dt_updated', 'py_type': 'datetime'},
            {'name': 'gnum', 'py_type': 'string'},
            {'name': 'vehicle_model', 'py_type': '/api/v1/dynamic/vehicle_model/'},
            {'name': 'finished_tasks_waste_weight', 'py_type': 'Decimal'},
        ]
    }
