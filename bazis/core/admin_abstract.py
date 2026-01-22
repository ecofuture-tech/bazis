from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.contrib.contenttypes.models import ContentType

from rangefilter.filters import DateTimeRangeFilter

from bazis.core.utils.sets_order import OrderedSet


class ContentTypeFilterMixin:
    """
    Mixin to filter queryset based on content type fields and base class.

    Tags: RAG, EXPORT
    """

    content_type__base_class = None
    content_type__fields = []

    def __init__(self, *args, **kwargs):
        """
        Initialize the ContentTypeFilterMixin and update filter_horizontal with relevant
        many-to-many fields.
        """
        super().__init__(*args, **kwargs)
        self.filter_horizontal = self.filter_horizontal + tuple(
            [f.name for f in self.opts.many_to_many if f.name in self.content_type__fields]
        )

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Customize the form field for foreign key relationships to filter by content type
        fields.
        """
        if self.content_type__fields and db_field.name in self.content_type__fields:
            content_type_id = [
                elem.id
                for elem in ContentType.objects.filter()
                if elem.model_class()
                and issubclass(elem.model_class(), self.content_type__base_class)
            ]
            kwargs['queryset'] = ContentType.objects.filter(id__in=content_type_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Customize the form field for many-to-many relationships to filter by content
        type fields.
        """

        def gen_statused_types():
            """
            Generator to yield content type IDs for models that are subclasses of the base
            class.
            """
            for c_type in ContentType.objects.all():
                model_class = c_type.model_class()
                if model_class and issubclass(model_class, self.content_type__base_class):
                    yield c_type.id

        if db_field.name in self.content_type__fields:
            kwargs['queryset'] = ContentType.objects.filter(id__in=list(gen_statused_types()))
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class M2mThroughMixin:
    """
    Mixin to handle many-to-many relationships with intermediary models in Django
    admin.

    Tags: RAG, EXPORT
    """

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Customize the form field for many-to-many relationships to set intermediary
        model as auto-created.
        """
        db_field.remote_field.through._meta.auto_created = True
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class DtAdminMixin:
    """
    Mixin to add datetime-related fields and filters to Django admin.

    Tags: RAG, EXPORT
    """

    ordering = ['-dt_updated']

    def get_list_display(self, request):
        """
        Extend the list display in Django admin to include 'dt_updated' field.
        """
        return tuple(OrderedSet(super().get_list_display(request) + ('dt_updated',)))

    def get_search_fields(self, request):
        """
        Extend the search fields in Django admin to include 'id' field.
        """
        return tuple(OrderedSet(super().get_search_fields(request) + ('id',)))

    def get_readonly_fields(self, request, obj=None):
        """
        Extend the readonly fields in Django admin to include 'dt_created' and
        'dt_updated' fields.
        """
        return tuple(
            OrderedSet(
                super().get_readonly_fields(request, obj)
                + (
                    'dt_created',
                    'dt_updated',
                )
            )
        )

    def get_list_filter(self, request):
        """
        Extend the list filters in Django admin to include 'dt_created' field with a
        DateTimeRangeFilter.
        """
        return (('dt_created', DateTimeRangeFilter),) + super().get_list_filter(request)


class AutocompleteMixin:
    """
    Mixin to use autocomplete widgets for foreign key and many-to-many fields in
    Django admin.

    Tags: RAG, EXPORT
    """

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Customize the form field for foreign key relationships to use an
        AutocompleteSelect widget.
        """
        db = kwargs.get('using')

        if 'widget' not in kwargs:
            kwargs['widget'] = AutocompleteSelect(
                db_field, self.admin_site, using=db, attrs={'style': 'width: 300px;'}
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Customize the form field for many-to-many relationships to use an
        AutocompleteSelectMultiple widget, unless an intermediary model is not auto-
        created.
        """
        if not db_field.remote_field.through._meta.auto_created:
            return None
        db = kwargs.get('using')

        if 'widget' not in kwargs and not self.filter_horizontal:
            kwargs['widget'] = AutocompleteSelectMultiple(
                db_field, self.admin_site, using=db, attrs={'style': 'width: 300px'}
            )

        return super().formfield_for_manytomany(db_field, request, **kwargs)


class UniqNumberAdminMixin:
    """
    Mixin to add 'uniq_number' field to readonly fields, list display, and search
    fields in Django admin.

    Tags: RAG, EXPORT
    """

    def get_readonly_fields(self, request, obj=None):
        """
        Extend the readonly fields in Django admin to include 'uniq_number' field.
        """
        return ('uniq_number',) + super().get_readonly_fields(request)

    def get_list_display(self, request):
        """
        Extend the list display in Django admin to include 'uniq_number' field.
        """
        return super().get_list_display(request) + ('uniq_number',)

    def get_search_fields(self, request):
        """
        Extend the search fields in Django admin to include 'uniq_number' field.
        """
        return super().get_search_fields(request) + ('uniq_number',)
