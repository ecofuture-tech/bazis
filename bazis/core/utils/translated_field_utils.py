from django.conf import settings
from django.utils.translation import get_language

from translated_fields import to_attribute


def translated_attrgetter(name, field):
    def _getter(self):
        val = getattr(self, to_attribute(name, get_language() or field.languages[0]))
        if not val:
            for lang in field.languages:
                val = getattr(self, to_attribute(name, lang))
                if val:
                    break
        return val

    return _getter


def fill_default_language_fields(model):
    # Get the current default language
    default_language = settings.LANGUAGE_CODE

    # List of all available languages from settings
    available_languages = [lang[0] for lang in settings.LANGUAGES]

    # Automatically find all translatable fields
    # TranslatedField creates fields with language suffixes
    model_fields = {f.name for f in model._meta.get_fields()}

    # Find the base names of translatable fields
    translated_fields = set()
    for field_name in model_fields:
        # Check whether the field ends with a language code
        for lang in available_languages:
            if field_name.endswith(f'_{lang}'):
                # Extract the base field name
                base_name = field_name[: -len(f'_{lang}')]
                translated_fields.add(base_name)
                break

    print(f'Found translatable fields: {translated_fields}')

    for obj in model.objects.all():
        updated = False

        for field_name in translated_fields:
            # Name of the default field (for example, title_en)
            default_field = f'{field_name}_{default_language.split("-")[0]}'

            # Check whether the default field is empty
            default_value = getattr(obj, default_field, None)

            if not default_value:
                # Find the first non-empty value among all languages
                for lang in available_languages:
                    lang_code = lang.split('-')[0]
                    lang_field = f'{field_name}_{lang_code}'

                    try:
                        lang_value = getattr(obj, lang_field, None)
                        if lang_value:
                            setattr(obj, default_field, lang_value)
                            updated = True
                            break
                    except AttributeError:
                        continue

        if updated:
            obj.save()
