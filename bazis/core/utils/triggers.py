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

import hashlib

from django.db import models

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
