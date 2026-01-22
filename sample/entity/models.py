"""
# Demonstration of calculated fields in Django models

## Structure of `FieldCalc` descendants:
- `FieldRelated` — access to data of records referenced in the current table as FK (`select_related`).
- `FieldAnnotate`:
  - `FieldAggr` — applying SQL functions to fields of tables where the current model is an FK. Not used.
  - `FieldSubquery`:
    - `FieldSubAggr` — subquery with aggregate functions.
    - `FieldIsExists` — checks for the existence of records by conditions in the table where the current FK is.
- `FieldJson` — inherits from `FieldRelated` and `FieldSubquery`.

Common attributes:
    source: str
    query: Q | Expression = None
    alias: str = None
    context: list[str] = None
Related:
    slice: slice = None
    nested: list['FieldCalc'] = dataclasses.field(default_factory=list)
    fields: list[str] = dataclasses.field(default_factory=list)
    order_by: list[str] = None
    filter_fn: Callable[[QuerySet, dict], QuerySet] = None
Aggr
    func: Type[Func] = None
Subquery
    filter_fn: Callable[[QuerySet, dict], QuerySet] = None
SubAggr
    func: str = None
IsExists
    nested: list['FieldSubquery'] = dataclasses.field(default_factory=list)
Individual attributes:
    slice exists only for Json.
    order_by exists only for Json, because only it returns a list of elements.
    fields exist only for Json.
    nested exists for Related and Json and IsExists, and does not exist for Aggregates.
    func exists only for Aggr and SubAggr, Django aggregates or a string. It is recommended to use SubAggr.
    filter_fn exists for all except Aggr. TODO Cases.
Common attributes
    query - there are examples only for IsExists and SubAggr.
    context - there are examples for Json and Related.
    source
    alias - Required for Aggregates, IsExists and in the Related (Dynamic) hierarchy, in the json hierarchy it is auto-filled.
"""

from decimal import Decimal

from django.db import models
from django.db.models import F, Q, Sum

from bazis_test_utils.models_abstract import (
    ChildEntityBase,
    DependentEntityBase,
    ExtendedEntityBase,
    ParentEntityBase,
)

from bazis.core.fields import ChoiceArrayField
from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin
from bazis.core.utils.functools import get_attr
from bazis.core.utils.orm import (
    FieldAggr,
    FieldIsExists,
    FieldJson,
    FieldRelated,
    FieldSubAggr,
    calc_property,
)


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
            FieldJson(source='drivers', context=['_user'], query=Q(org_owner=F('_organization'))),
        ]
    )
    def drivers_list(self) -> list:
        return [
            {
                'id': driver['id'],
            }
            for driver in self._drivers
        ]

    @calc_property(
        [
            FieldJson('drivers1'),
        ]
    )
    def drivers_list1(self) -> list:
        return [
            {
                'id': driver['id'],
            }
            for driver in get_attr(self, '_drivers1') or []
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
            FieldJson(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'vehicle_id'],
                nested=[
                    FieldJson(
                        source='vehicle',
                        fields=['gnum', 'dt_created'],
                        nested=[FieldJson(source='vehicle_model', fields=['engine_type'])],
                    )
                ],
            ),
        ]
    )
    def carrier_tasks_json_hierarchy(self) -> list:
        return [
            {
                'id': task['id'],
                'dt_start': task['dt_start'],
                'dt_finish': task['dt_finish'],
                'fact_waste_weight': task['fact_waste_weight'],
                'vehicle_gnum': get_attr(task, '_vehicle.0.gnum'),
            }
            for task in self._carrier_tasks
        ]

    @calc_property(
        [
            FieldJson(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'vehicle_id'],
                context=['_organization'],
                query=Q(org_owner=F('_organization')),
                nested=[
                    FieldJson(
                        source='vehicle',
                        fields=['gnum', 'dt_created'],
                        nested=[FieldJson(source='vehicle_model', fields=['engine_type'])],
                    )
                ],
            ),
        ]
    )
    def carrier_tasks_context(self) -> list:
        return [
            {
                'id': task['id'],
                'dt_start': task['dt_start'],
                'dt_finish': task['dt_finish'],
                'fact_waste_weight': task['fact_waste_weight'],
                'vehicle_gnum': get_attr(task, '_vehicle.0.gnum'),
            }
            for task in self._carrier_tasks
        ]

    @calc_property(
        [
            FieldJson(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_finish__isnull=False),
                slice=slice(1),
                order_by=['-dt_finish'],
            ),
        ]
    )
    def last_trip(self) -> dict:
        return {
            'id': get_attr(self, '_carrier_tasks.0.id'),
            'dt_start': get_attr(self, '_carrier_tasks.0.dt_start'),
            'dt_finish': get_attr(self, '_carrier_tasks.0.dt_finish'),
            'fact_waste_weight': get_attr(self, '_carrier_tasks.0.fact_waste_weight'),
        }

    @calc_property(
        [
            FieldJson(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight'],
                query=Q(dt_finish__isnull=False),
                order_by=['dt_start'],
            ),
        ]
    )
    def trips(self) -> list:
        return [
            {
                'id': trips['id'],
                'dt_start': trips['dt_start'],
                'dt_finish': trips['dt_finish'],
                'fact_waste_weight': trips['fact_waste_weight'],
            }
            for trips in self._carrier_tasks
        ]

    class Meta:
        verbose_name = 'Driver'
        verbose_name_plural = 'Drivers'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class Vehicle(DtMixin, UuidMixin, JsonApiMixin):
    """Vehicle with calculated fields."""

    vehicle_model = models.ForeignKey(
        VehicleModel, verbose_name='Vehicle Model', on_delete=models.CASCADE
    )
    country = models.ForeignKey(Country, verbose_name='Country', on_delete=models.CASCADE)
    gnum = models.CharField('State Registration Number', max_length=50, unique=True)

    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_capacity_1(self) -> Decimal:
        return get_attr(self, 'vehicle_model.capacity', Decimal(0.00))

    """
    FieldRelated
    data about the vehicle capacity from the table that is linked by a foreign key in the current model
    we return the value of a single field from the related table
    implementation option 2
    """

    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_capacity_2(self) -> Decimal:
        return get_attr(self.vehicle_model, 'capacity', Decimal(0.00))

    """
    FieldRelated
    data about the vehicle capacity from the table that is linked by a foreign key in the current model
    we return the value of a single field from the related table
    implementation option 3
    """

    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_capacity_3(self) -> Decimal:
        return self.vehicle_model.capacity

    """
    FieldRelated - data about the vehicle model name and model characteristics
    from the table that is linked by a foreign key in the current model
    we return a dictionary with data from several fields of the related table
    """

    @calc_property([FieldRelated('vehicle_model')])
    def vehicle_model_info(self) -> dict:
        return {
            'model': self.vehicle_model.model,
            'capacity': self.vehicle_model.capacity,
        }

    @calc_property(
        [
            FieldRelated(
                'vehicle_model',
                alias='_vehicle_model',
                nested=[FieldRelated('brand', alias='_brand')],
            )
        ]
    )
    def brand_info(self) -> dict:
        return {
            'id': self.vehicle_model.brand.id,
            'name': self.vehicle_model.brand.name,
        }

    # @calc_property([FieldRelated('vehicle_model__brand')])
    # def brand_info(self) -> dict:
    #     return {
    #         'id': self.vehicle_model.brand.id,
    #         'name': self.vehicle_model.brand.name,
    #     }

    @calc_property([FieldRelated('vehicle_model__brand'), FieldRelated('country')])
    def brand_and_country(self) -> dict:
        return {
            'brand': self.vehicle_model.brand.name,
            'country': self.country.name,
        }

    @calc_property(
        [
            FieldAggr(
                source='carrier_tasks__fact_waste_weight',
                func=Sum,
                alias='current_tasks_waste_weight_aggr',
                query=Q(carrier_tasks__dt_start__isnull=False)
                & Q(carrier_tasks__dt_finish__isnull=True),
            ),
        ],
        as_filter=True,
    )
    def current_tasks_waste_weight_aggr(self) -> Decimal | None:
        return get_attr(self, 'current_tasks_waste_weight_aggr', Decimal(0))

    @calc_property(
        [
            FieldSubAggr(
                source='carrier_tasks__fact_waste_weight',
                func='Sum',
                alias='current_tasks_waste_weight_subaggr',
                query=Q(dt_start__isnull=False) & Q(dt_finish__isnull=True),
            ),
        ]
    )
    def current_tasks_waste_weight_subaggr(self) -> Decimal | None:
        return get_attr(self, 'current_tasks_waste_weight_subaggr', Decimal(0))

    @calc_property(
        [
            FieldIsExists(
                source='carrier_tasks',
                query=Q(dt_start__isnull=False) & ~Q(dt_finish__isnull=False),
                alias='has_active_trip',
            ),
        ],
        as_filter=True,
    )
    def has_active_trip(self) -> bool:
        return get_attr(self, 'has_active_trip', False)

    @calc_property(
        [
            FieldIsExists(
                source='carrier_tasks',
                alias='has_active_trip_with_phone_join',
                query=Q(dt_start__isnull=False)
                & Q(dt_finish__isnull=True)
                & Q(driver__contact_phone__isnull=False)
                & ~Q(driver__contact_phone=''),
            )
        ]
    )
    def has_active_trip_with_phone_join(self) -> bool:
        return get_attr(self, 'has_active_trip_with_phone_join', False)

    @calc_property(
        [
            FieldIsExists(
                source='carrier_tasks',
                alias='has_active_trip_with_phone_subquery',
                query=Q(dt_start__isnull=False)
                & Q(dt_finish__isnull=True)
                & Q(_has_drivers_with_phone=True),
                nested=[
                    FieldIsExists(
                        source='driver',
                        alias='_has_drivers_with_phone',
                        query=Q(contact_phone__isnull=False) & ~Q(contact_phone=''),
                    )
                ],
            )
        ]
    )
    def has_active_trip_with_phone_subquery(self) -> bool:
        return get_attr(self, 'has_active_trip_with_phone_subquery', False)

    @calc_property(
        [
            FieldJson(
                source='carrier_tasks',
                fields=['id', 'dt_start', 'dt_finish', 'fact_waste_weight', 'driver_id'],
            ),
        ]
    )
    def carrier_task_list(self) -> list:
        return [
            {
                'id': task['id'],
                'dt_start': task['dt_start'],
                'dt_finish': task['dt_finish'],
                'fact_waste_weight': task['fact_waste_weight'],
                'driver_id': task['driver_id'],
            }
            for task in self._carrier_tasks
        ]

    class Meta:
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'

    def __str__(self):
        return self.gnum


class CarrierTask(DtMixin, UuidMixin, JsonApiMixin):
    """Register of transportations."""

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
        'Organization',
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = 'Carrier Task'
        verbose_name_plural = 'Carrier Tasks'
        indexes = [
            models.Index(fields=['vehicle', 'dt_start', 'dt_finish'], name='ix_vehicle_dates'),
        ]

    def __str__(self):
        return f'Carrier Task {self.id}'


class ChildEntity(ChildEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    pass


class DependentEntity(DependentEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    parent_entity = models.ForeignKey(
        'ParentEntity', on_delete=models.CASCADE, related_name='dependent_entities'
    )


class DependentEntityNull(DependentEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    parent_entity = models.ForeignKey(
        'ParentEntity', on_delete=models.CASCADE, related_name='dependent_entities_null', null=True
    )


class ExtendedEntity(ExtendedEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    parent_entity = models.OneToOneField(
        'ParentEntity', on_delete=models.CASCADE, related_name='extended_entity'
    )


class ExtendedEntityNull(ExtendedEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    parent_entity = models.OneToOneField(
        'ParentEntity', on_delete=models.CASCADE, related_name='extended_entity_null', null=True
    )


class ParentEntityState(models.TextChoices):
    STATE_ONE = (
        'state_one',
        'State one',
    )
    STATE_TWO = (
        'state_two',
        'State two',
    )
    STATE_THREE = (
        'state_three',
        'State three',
    )
    STATE_FOUR = (
        'state_four',
        'State four',
    )


class ParentEntityField(models.TextChoices):
    FIRST_FIELD = (
        'first_field',
        'First field',
    )
    SECOND_FIELD = (
        'second_field',
        'Second field',
    )
    THIRD_FIELD = (
        'third_field',
        'Third field',
    )


class ParentEntity(ParentEntityBase, DtMixin, UuidMixin, JsonApiMixin):
    child_entities = models.ManyToManyField(
        ChildEntity,
        related_name='parent_entities',
        blank=True,
    )
    state = models.CharField(
        'State',
        max_length=255,
        choices=ParentEntityState,
        default=ParentEntityState.STATE_ONE.value,
    )
    field = ChoiceArrayField(
        models.CharField(choices=ParentEntityField, max_length=32),
        verbose_name='Field',
        blank=True,
        null=True,
    )

    @calc_property([FieldRelated('extended_entity')])
    def extended_entity_price(self) -> Decimal:
        return get_attr(self, 'extended_entity.extended_price', Decimal(0.00))

    @calc_property(
        [
            FieldJson(
                source='child_entities',
                query=Q(child_is_active=True),
                fields=['id', 'child_name', 'child_description', 'child_is_active'],
            ),
        ]
    )
    def active_children(self) -> list:
        return [
            {
                'id': child['id'],
                'child_name': child['child_name'],
                'child_description': child['child_description'],
                'child_is_active': child['child_is_active'],
            }
            for child in self._child_entities
        ]

    @calc_property(
        [
            FieldSubAggr(
                'child_entities',
                query=Q(child_is_active=True),
                func='Count',
                alias='count_active_children',
            ),
        ]
    )
    def count_active_children(self) -> int:
        return self.count_active_children

    @calc_property(
        [
            FieldIsExists(
                'child_entities',
                query=Q(child_price__isnull=True) | Q(child_is_active=False),
                alias='has_inactive_children',
            ),
        ],
        as_filter=True,
    )
    def has_inactive_children(self) -> bool:
        return getattr(self, 'has_inactive_children', False)


class WithProtectedEntity(DtMixin, UuidMixin, JsonApiMixin):
    name = models.CharField(max_length=255)
    child = models.ForeignKey(
        ChildEntity,
        on_delete=models.PROTECT,
    )

    class Meta:
        verbose_name = 'Entity with Protected'
        verbose_name_plural = 'Entities with Protected'


class WithProtectedEntitySystem(DtMixin, UuidMixin):
    name = models.CharField(max_length=255)
    child = models.ForeignKey(
        ChildEntity,
        on_delete=models.PROTECT,
    )

    class Meta:
        verbose_name = 'Entity with Protected System'
        verbose_name_plural = 'Entities with Protected System'
