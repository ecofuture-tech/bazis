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

from decimal import Decimal
from typing import Any

from django.db import models
from django.db.models import F, Q

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin
from bazis.core.utils.orm import DependsCalc, FieldDynamic, calc_property


class Organization(DtMixin, UuidMixin, JsonApiMixin):
    """Division."""

    name = models.CharField(max_length=255)


class VehicleBrand(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle brand."""

    name = models.CharField('Brand Name', max_length=255, unique=True)

    class Meta:
        verbose_name = 'Vehicle Brand'
        verbose_name_plural = 'Vehicle Brands'

    def __str__(self):
        return self.name


class Country(DtMixin, UuidMixin, JsonApiMixin):
    """Country."""

    name = models.CharField('Country Name', max_length=255, unique=True)

    class Meta:
        verbose_name = 'Country'
        verbose_name_plural = 'Countries'

    def __str__(self):
        return self.name


class VehicleModel(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle model."""

    brand = models.ForeignKey(VehicleBrand, verbose_name='Brand', on_delete=models.CASCADE)
    model = models.CharField('Model', max_length=255, unique=True)
    engine_type = models.CharField('Engine Type', max_length=50, null=True, blank=True)
    capacity = models.DecimalField(
        'Capacity, t', max_digits=6, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Vehicle Model'
        verbose_name_plural = 'Vehicle Models'
        unique_together = ('brand', 'model')

    def __str__(self):
        return self.model


class Division(DtMixin, UuidMixin, JsonApiMixin):
    """Division."""

    name = models.CharField(max_length=255)
    org_owner = models.ForeignKey(
        'Organization',
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
    )

    @calc_property(
        [
            FieldDynamic(
                source='drivers', context=['_user'], query=Q(org_owner=F('_organization'))
            ),
        ]
    )
    def drivers_list(self, dc: DependsCalc) -> list:
        return [
            {
                'id': driver.id,
            }
            for driver in dc.data.drivers
        ]

    @calc_property(
        [
            FieldDynamic('drivers1'),
        ]
    )
    def drivers_list1(self, dc: DependsCalc) -> list:
        return [
            {
                'id': driver.get('id'),
            }
            for driver in dc.data.drivers1 or []
        ]


class Driver(DtMixin, UuidMixin, JsonApiMixin):
    """Driver."""

    first_name = models.CharField('First Name', max_length=255)
    last_name = models.CharField('Last Name', max_length=255)
    contact_phone = models.CharField('Phone', max_length=50, null=True, blank=True)

    divisions = models.ManyToManyField(
        Division,
        related_name='drivers',
        blank=True,
    )
    org_owner = models.ForeignKey(
        'Organization',
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
    )

    @calc_property(
        [
            FieldDynamic(
                source='divisions',
                fields=['id', 'name', 'dt_created'],
            ),
        ]
    )
    def divisions_hired_info(self, dc: DependsCalc) -> list:
        return [
            {
                'id': division.id,
                'division': division.name,
                'hired_date': division.dt_created,
            }
            for division in dc.data.divisions
        ]

    class Meta:
        verbose_name = 'Driver'
        verbose_name_plural = 'Drivers'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class Vehicle(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle."""

    vehicle_model = models.ForeignKey(
        VehicleModel, verbose_name='Vehicle Model', on_delete=models.CASCADE
    )
    gnum = models.CharField('State Registration Number', max_length=50, unique=True)

    @calc_property([FieldDynamic('vehicle_model')], as_filter=True)
    def vehicle_capacity(self, dc: DependsCalc) -> Decimal:
        return dc.data.vehicle_model.capacity

    @calc_property([FieldDynamic('vehicle_model')])
    def vehicle_model_info(self, dc: DependsCalc) -> dict:
        return {
            'model': dc.data.vehicle_model.model,
            'capacity': dc.data.vehicle_model.capacity,
        }

    @calc_property([FieldDynamic('assemble_info')], as_filter=True)
    def vehicle_assemble_info(self, dc: DependsCalc) -> dict[str, Any]:
        return {
            'assembly_date': dc.data.assemble_info.assembly_date,
            'assembly_plant': dc.data.assemble_info.assembly_plant,
        }

    @calc_property(
        [FieldDynamic('vehicle_model').add_nested([FieldDynamic('brand')])], as_filter=True
    )
    def brand_info(self, dc: DependsCalc) -> dict:
        return {
            'id': dc.data.vehicle_model.brand.id,
            'name': dc.data.vehicle_model.brand.name,
        }

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks__fact_waste_weight',
                func='Sum',
                alias='finished_tasks_waste_weight',
                query=Q(dt_finish__isnull=False),
            ),
        ],
        as_filter=True,
    )
    def finished_tasks_waste_weight(self, dc: DependsCalc) -> Decimal | None:
        return dc.data.finished_tasks_waste_weight

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

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks',
                alias='has_active_trip_with_phone',
                query=Q(dt_start__isnull=False)
                & Q(dt_finish__isnull=True)
                & Q(has_drivers_with_phone=True),
            ).add_nested(
                [
                    FieldDynamic(
                        source='driver',
                        alias='has_drivers_with_phone',
                        query=Q(contact_phone__isnull=False) & ~Q(contact_phone=''),
                    )
                ]
            )
        ]
    )
    def has_active_trip_with_phone(self, dc: DependsCalc) -> bool:
        return dc.data.has_active_trip_with_phone

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

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks', fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight']
            ).add_nested(
                [
                    FieldDynamic(source='driver', fields=['last_name']).add_nested(
                        [FieldDynamic(source='org_owner', fields=['name'])]
                    )
                ]
            )
        ]
    )
    def carrier_tasks_json_hierarchy(self, dc: DependsCalc) -> list:
        return [
            {
                'id': task.id,
                'dt_start': task.dt_start,
                'dt_finish': task.dt_finish,
                'fact_waste_weight': task.fact_waste_weight,
                'last_name': task.driver[0].last_name,
                'organization': task.driver[0].org_owner[0].name,
            }
            for task in dc.data.carrier_tasks
        ]

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True),
                order_by=['dt_start'],
            ),
        ]
    )
    def active_trips(self, dc: DependsCalc) -> list:
        return [
            {
                'id': trips.id,
                'dt_start': trips.dt_start,
                'dt_finish': trips.dt_finish,
                'fact_waste_weight': trips.fact_waste_weight,
            }
            for trips in dc.data.carrier_tasks
        ]

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_finish__isnull=False),
                slice=slice(1),
                order_by=['-dt_finish'],
            ),
        ]
    )
    def last_trip(self, dc: DependsCalc) -> dict:
        return (
            {
                'id': dc.data.carrier_tasks[0].id,
                'dt_start': dc.data.carrier_tasks[0].dt_start,
                'dt_finish': dc.data.carrier_tasks[0].dt_finish,
                'fact_waste_weight': dc.data.carrier_tasks[0].fact_waste_weight,
            }
            if dc.data.carrier_tasks
            else dict()
        )

    @calc_property(
        [
            FieldDynamic(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                context=['_organization'],
                query=Q(org_owner=F('_organization')),
            ).add_nested(
                [
                    FieldDynamic(source='driver', fields=['contact_phone']).add_nested(
                        [FieldDynamic(source='org_owner', fields=['name'])]
                    )
                ]
            )
        ]
    )
    def carrier_tasks_context(self, dc: DependsCalc) -> list:
        return [
            {
                'id': task.id,
                'dt_start': task.dt_start,
                'dt_finish': task.dt_finish,
                'fact_waste_weight': task.fact_waste_weight,
                'driver_phone': task.driver[0].contact_phone,
                'organization': task.driver[0].org_owner[0].name,
            }
            for task in dc.data.carrier_tasks
        ]

    class Meta:
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'

    def __str__(self):
        return self.gnum


class VehicleAssembleInfo(DtMixin, UuidMixin, JsonApiMixin):
    """Assembly information for the vehicle."""

    assembly_plant = models.CharField('Assembly plant', max_length=50)
    assembly_date = models.DateField('Assembly date')
    country = models.ForeignKey(Country, verbose_name='Country', on_delete=models.CASCADE)

    vin = models.CharField('VIN', max_length=17, unique=True)

    vehicle = models.OneToOneField(
        Vehicle,
        verbose_name='Vehicle',
        related_name='assemble_info',
        on_delete=models.CASCADE,
    )


class CarrierTask(DtMixin, UuidMixin, JsonApiMixin):
    """Transport register."""

    vehicle = models.ForeignKey(
        Vehicle, verbose_name='Vehicle', related_name='carrier_tasks', on_delete=models.CASCADE
    )
    driver = models.ForeignKey(
        Driver, verbose_name='Driver', related_name='carrier_tasks', on_delete=models.CASCADE
    )
    dt_start = models.DateTimeField('Start Time', null=True, blank=True)
    dt_finish = models.DateTimeField('Start Time', null=True, blank=True)
    fact_waste_weight = models.DecimalField(
        'Fact Waste Weight, t', max_digits=15, decimal_places=3, null=True, blank=True
    )
    org_owner = models.ForeignKey(
        Organization, blank=True, null=True, db_index=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = 'Carrier Task'
        verbose_name_plural = 'Carrier Tasks'

    def __str__(self):
        return f'Carrier Task {self.id}'
