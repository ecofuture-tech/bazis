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

from django.apps import AppConfig, apps


class BaseConfigMeta(type):
    """
    Metaclass for automatic default app detection.
    Returns True for 'default' attribute if class has no subclasses.
    Used to determine primary app config when multiple configs exist.
    """

    def __getattr__(cls, name):
        """
        Provides dynamic 'default' attribute based on subclass existence.
        Returns True if no subclasses (is leaf config), False otherwise.
        """
        if name == 'default':
            if cls.__subclasses__():
                return False
            else:
                return True
        raise AttributeError


class BaseConfig(AppConfig, metaclass=BaseConfigMeta):
    """
    The AppConfig of a Bazis package or app: BaseConfigMeta makes the subclass of an app
    its default config. Django finds its management commands, and its `static` and
    `templates` directories with the app directories finder and loader (`APP_DIRS`).

    Tags: RAG, EXPORT
    """


def get_ref_model(model_name):
    """
    Safely retrieves Django model by name string.

    Args:
        model_name: Model reference string (e.g., 'app_label.ModelName')

    Returns:
        Model class or None if not found

    Uses require_ready=False to allow retrieval during app initialization.

    RAG keywords: model lookup, get model, django model, model reference
    """
    try:
        return apps.get_model(model_name, require_ready=False)
    except LookupError:
        return None
