from django import forms
from django.contrib.postgres.fields import ArrayField


class ChoiceArrayField(ArrayField):
    """
    A custom Django model field to store an array of selected values using PostgreSQL's ArrayField
    and Django's MultipleChoiceField.

        This field integrates ArrayField from Django 1.9+ with MultipleChoiceField for form handling.

        Example usage::

            choices = ChoiceArrayField(
                models.CharField(
                    max_length=100,  # Maximum length for each choice
                    choices=(('choice1', 'Choice 1'), ('choice2', 'Choice 2')),  # List of choices
                ),
                default=['choice1']  # Default selected values
            )

    Tags: RAG, EXPORT
    """

    def __init__(self, base_field=None, static_label=None, **kwargs):
        """
        Initialize the ChoiceArrayField with the given base field and optional static label.

        :param base_field: The base field type for the array elements.
        :param static_label: An optional static label for the field.
        :param kwargs: Additional keyword arguments for the ArrayField.
        """
        self.static_label = static_label
        super().__init__(base_field, **kwargs)

    def formfield(self, **kwargs):
        """
        Return the MultipleChoiceField form field with the appropriate choices.

        :param kwargs: Additional keyword arguments for the form field.
        :return: A MultipleChoiceField form field instance.
        """
        defaults = {
            'form_class': forms.MultipleChoiceField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        # Skip our parent's formfield implementation completely as we don't
        # care for it.
        # pylint:disable=bad-super-call
        return super(ArrayField, self).formfield(**defaults)
