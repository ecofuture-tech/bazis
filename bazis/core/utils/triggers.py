import hashlib

from django.db import models

import pghistory
from pgtrigger.core import MAX_NAME_LENGTH


def trigger_name(name: str):
    """
    Generate a unique trigger name that complies with the maximum length constraint
    by truncating and appending a hash if necessary.

    Tags: RAG, EXPORT
    """
    if len(name) > MAX_NAME_LENGTH - 6:
        name = name[: MAX_NAME_LENGTH - 6] + hashlib.md5(name.encode()).hexdigest()[:6]
    return name


def register(*triggers, with_through=False):
    """
    Decorator to register triggers on a Django model, with an optional parameter to
    include through models for many-to-many relationships.

    Tags: RAG, EXPORT
    """

    def _model_wrapper(model_class):
        """
        Inner wrapper function for the register decorator that applies the trigger
        registration logic to a given model class.
        """

        def triggers_set(model):
            """
            Set triggers on the model, including through models for many-to-many
            relationships if specified.
            """
            if not model._meta.abstract and not model._meta.proxy:
                for trigger in triggers:
                    trigger._primary_model = model
                    trigger.register(model)

                    if with_through:
                        for m2m_field in model._meta.many_to_many:
                            through = getattr(model, m2m_field.name).through
                            if through._meta.auto_created:
                                trigger.register(through)

        def finalize(sender, **kwargs):
            """
            Signal handler to finalize trigger registration when the model class is
            prepared.
            """
            if not issubclass(sender, model_class):
                return
            triggers_set(sender)

        if model_class._meta.abstract:
            models.signals.class_prepared.connect(finalize, weak=False)
        else:
            triggers_set(model_class)

        return model_class

    return _model_wrapper


def history_track(*args, **kwargs):
    """
    Decorator to track history events on a Django model using pghistory, with
    support for many-to-many relationships.

    Tags: RAG, EXPORT
    """
    kwargs = {**{'context_field': pghistory.ContextJSONField()}, **kwargs}

    def _model_wrapper(model_class):
        """
        Inner wrapper function for the history_track decorator that applies the history
        tracking logic to a given model class.
        """

        def history_set(model):
            """
            Set history tracking on the model, including through models for many-to-many
            relationships if they are auto-created.
            """
            if not model._meta.abstract and not model._meta.proxy:
                pghistory.track(*args, **kwargs)(model)

                for m2m_field in model._meta.many_to_many:
                    through = getattr(model, m2m_field.name).through
                    if through._meta.auto_created:
                        pghistory.track(
                            pghistory.InsertEvent('add'),
                            pghistory.DeleteEvent('remove'),
                            **{**kwargs, **{'obj_field': None}},
                        )(through)

        def finalize(sender, **kwargs):
            """
            Signal handler to finalize history tracking when the model class is prepared.
            """
            if not issubclass(sender, model_class):
                return
            history_set(sender)

        if model_class._meta.abstract:
            models.signals.class_prepared.connect(finalize, weak=False)
        else:
            history_set(model_class)

        return model_class

    return _model_wrapper
