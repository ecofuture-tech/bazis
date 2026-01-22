# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.utils.timezone import now

import pytest
from dynamic.models import CarrierTask as DynamicCarrierTask
from dynamic.models import Country as DynamicCountry
from dynamic.models import Division as DynamicDivision
from dynamic.models import Driver as DynamicDriver
from dynamic.models import Organization as DynamicOrganization
from dynamic.models import Vehicle as DynamicVehicle
from dynamic.models import VehicleAssembleInfo
from dynamic.models import VehicleBrand as DynamicVehicleBrand
from dynamic.models import VehicleModel as DynamicVehicleModel
from entity.models import (
    CarrierTask,
    Country,
    Division,
    Driver,
    Organization,
    Vehicle,
    VehicleBrand,
    VehicleModel,
)
from route_injection.models import CarrierTask as RouteInjectionCarrierTask
from route_injection.models import Country as RouteInjectionCountry
from route_injection.models import Division as RouteInjectionDivision
from route_injection.models import Driver as RouteInjectionDriver
from route_injection.models import Organization as RouteInjectionOrganization
from route_injection.models import Vehicle as RouteInjectionVehicle
from route_injection.models import VehicleAssembleInfo as RouteInjectionVehicleAssembleInfo
from route_injection.models import VehicleBrand as RouteInjectionVehicleBrand
from route_injection.models import VehicleModel as RouteInjectionVehicleModel


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker) -> None:
    with django_db_blocker.unblock():
        call_command('pgtrigger', 'install')


@pytest.fixture(scope='function')
def sample_app():
    from sample.main import app

    return app


@pytest.fixture(scope='function', autouse=True)
def clear_sql_log():
    filename = 'sql.log'

    if os.path.exists(filename):
        open(filename, 'w').close()
    else:
        with open(filename, 'w'):
            pass


@pytest.fixture
def sample_vehicle_data(db):
    """Fixture for creating a test vehicle, driver, and routes."""

    organization = Organization.objects.create(
        name='Test Organization', id='3fa85f64-5717-4562-b3fc-2c963f66afa6'
    )
    division = Division.objects.create(name='Test Division', org_owner=organization)
    vehicle_brand = VehicleBrand.objects.create(name='Ford')
    vehicle_model = VehicleModel.objects.create(
        brand=vehicle_brand, model='m3', engine_type='Diesel', capacity=Decimal('3.50')
    )
    vehicle_country = Country.objects.create(name='Russia')
    vehicle = Vehicle.objects.create(
        vehicle_model=vehicle_model,
        country=vehicle_country,
        gnum='XYZ-123',
    )
    driver = Driver.objects.create(
        first_name='John', last_name='Doe', contact_phone='123-456-789', org_owner=organization
    )
    task1 = CarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('3.50'),
        org_owner=organization,
    )
    task2 = CarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )
    task3 = CarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now() - timedelta(hours=2),
        dt_finish=now() - timedelta(hours=1),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )

    return {
        'organization': organization,
        'division': division,
        'vehicle': vehicle,
        'driver': driver,
        'tasks': [task1, task2, task3],
        'vehicle_model': vehicle_model,
        'vehicle_brand': vehicle_brand,
        'vehicle_country': vehicle_country,
    }


@pytest.fixture
def dynamic_vehicle_data(db):
    """Fixture for creating a test vehicle, driver, division, and routes."""

    organization = DynamicOrganization.objects.create(
        name='Test Organization', id='3fa85f64-5717-4562-b3fc-2c963f66afa6'
    )

    division = DynamicDivision.objects.create(name='Test Division', org_owner=organization)

    vehicle_brand = DynamicVehicleBrand.objects.create(name='Ford')

    vehicle_model = DynamicVehicleModel.objects.create(
        brand=vehicle_brand, model='m3', engine_type='Diesel', capacity=Decimal('3.50')
    )

    vehicle_country = DynamicCountry.objects.create(name='Russia')

    vehicle = DynamicVehicle.objects.create(
        vehicle_model=vehicle_model,
        gnum='XYZ-123',
    )

    driver = DynamicDriver.objects.create(
        first_name='John', last_name='Doe', contact_phone='123-456-789', org_owner=organization
    )

    driver.divisions.add(division)

    task1 = DynamicCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('3.50'),
        org_owner=organization,
    )

    task2 = DynamicCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )

    task3 = DynamicCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now() - timedelta(hours=2),
        dt_finish=now() - timedelta(hours=1),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )

    assemble_info = VehicleAssembleInfo.objects.create(
        assembly_plant='Plant A',
        assembly_date=date(2020, 5, 15),
        country=vehicle_country,
        vin='1HGCM82633A004352',
        vehicle=vehicle,
    )

    return {
        'organization': organization,
        'division': division,
        'vehicle': vehicle,
        'driver': driver,
        'tasks': [task1, task2, task3],
        'vehicle_model': vehicle_model,
        'vehicle_brand': vehicle_brand,
        'vehicle_country': vehicle_country,
        'assemble_info': assemble_info,
    }


@pytest.fixture
def route_injection_vehicle_data(db):
    """Fixture for creating a test vehicle, driver, division, and routes."""

    organization = RouteInjectionOrganization.objects.create(
        name='Test Organization', id='3fa85f64-5717-4562-b3fc-2c963f66afa6'
    )

    division = RouteInjectionDivision.objects.create(name='Test Division', org_owner=organization)

    vehicle_brand = RouteInjectionVehicleBrand.objects.create(name='Ford')

    vehicle_model = RouteInjectionVehicleModel.objects.create(
        brand=vehicle_brand, model='m3', engine_type='Diesel', capacity=Decimal('3.50')
    )

    vehicle_country = RouteInjectionCountry.objects.create(name='Russia')

    vehicle = RouteInjectionVehicle.objects.create(
        vehicle_model=vehicle_model,
        gnum='XYZ-123',
    )

    driver = RouteInjectionDriver.objects.create(
        first_name='John', last_name='Doe', contact_phone='123-456-789', org_owner=organization
    )

    driver2 = RouteInjectionDriver.objects.create(
        first_name='Bob', last_name='Lee', contact_phone='123-456-719', org_owner=organization
    )

    driver.divisions.add(division)

    task1 = RouteInjectionCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('3.50'),
        org_owner=organization,
    )

    task2 = RouteInjectionCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now(),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )

    task3 = RouteInjectionCarrierTask.objects.create(
        vehicle=vehicle,
        driver=driver,
        dt_start=now() - timedelta(hours=2),
        dt_finish=now() - timedelta(hours=1),
        fact_waste_weight=Decimal('4.50'),
        org_owner=organization,
    )

    assemble_info = RouteInjectionVehicleAssembleInfo.objects.create(
        assembly_plant='Plant A',
        assembly_date=date(2020, 5, 15),
        country=vehicle_country,
        vin='1HGCM82633A004352',
        vehicle=vehicle,
    )

    return {
        'organization': organization,
        'division': division,
        'vehicle': vehicle,
        'driver': driver,
        'driver2': driver2,
        'tasks': [task1, task2, task3],
        'vehicle_model': vehicle_model,
        'vehicle_brand': vehicle_brand,
        'vehicle_country': vehicle_country,
        'assemble_info': assemble_info,
    }
