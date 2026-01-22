import os
import random
from decimal import Decimal

import django
from django.utils.timezone import now

from route_injection.models import (
    CarrierTask,
    Country,
    Driver,
    Organization,
    Vehicle,
    VehicleBrand,
    VehicleModel,
)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sample.settings')
django.setup()

NUM_ORGS = 5
NUM_COUNTRIES = 5
NUM_BRANDS = 10
NUM_MODELS = 10
NUM_VEHICLES = 100
NUM_DRIVERS = 300
TASKS_PER_DRIVER = 10


def generate_test_data():
    print('Creating organizations, brands, models, countries...')

    orgs = [Organization.objects.create(name=f'Org __#{i}') for i in range(NUM_ORGS)]

    [Country.objects.create(name=f'Country __#{i}') for i in range(NUM_COUNTRIES)]

    brands = [VehicleBrand.objects.create(name=f'Brand __#{i}') for i in range(NUM_BRANDS)]

    models = [
        VehicleModel.objects.create(
            brand=random.choice(brands),
            model=f'Model __#{i}',
            engine_type=random.choice(['Diesel', 'Petrol', 'Electric']),
            capacity=Decimal(random.uniform(1.0, 10.0)).quantize(Decimal('0.01')),
        )
        for i in range(NUM_MODELS)
    ]

    print('Creating vehicles...')

    vehicles = [
        Vehicle.objects.create(vehicle_model=random.choice(models), gnum=f'VEH-{i:05d}')
        for i in range(NUM_VEHICLES)
    ]

    print('Creating drivers and trips...')

    for i in range(NUM_DRIVERS):
        driver = Driver.objects.create(
            first_name=f'Driver{i}',
            last_name='Testov',
            contact_phone=f'8-977-899-{1000 + i}',
            org_owner=random.choice(orgs),
        )

        vehicle = random.choice(vehicles)

        for j in range(TASKS_PER_DRIVER):
            CarrierTask.objects.create(
                vehicle=vehicle,
                driver=driver,
                dt_start=now(),
                dt_finish=None if j % 2 == 0 else now(),
                fact_waste_weight=Decimal(random.uniform(1.0, 10.0)).quantize(Decimal('0.1')),
                org_owner=driver.org_owner,
            )

        if i % 200 == 0:
            print(f'Drivers created: {i}')

    print(
        f'Total: {NUM_DRIVERS} drivers, {NUM_DRIVERS * TASKS_PER_DRIVER} trips, {NUM_VEHICLES} vehicles.'
    )


if __name__ == '__main__':
    generate_test_data()
