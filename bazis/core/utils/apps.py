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

import importlib.util
import os
from pathlib import Path

from django.apps import AppConfig, apps
from django.conf import settings
from django.core.management import get_commands, load_command_class


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
    Enhanced Django AppConfig with auto-discovery features.

    Automatically registers:
    - Management commands from app's management/commands/
    - Static files from app's static/ directory

    Inherits from Django's AppConfig and uses BaseConfigMeta.

    Tags: RAG, EXPORT
    """

    def ready(self):
        """
        Django lifecycle hook called when app is ready.

        Walks through class MRO (Method Resolution Order) to:
        1. Register management commands for each app in hierarchy
        2. Auto-discover and register static directories

        Processes parent classes in reverse MRO order to handle inheritance.

        RAG keywords: app ready, lifecycle, command discovery, static discovery
        """
        for cl in reversed(self.__class__.mro()):
            if hasattr(cl, 'name'):
                app_path = os.path.dirname(importlib.util.find_spec(cl.name).origin)
                self.register_app_commands(cl.name, app_path)
                # self.setup_locales(app_path)  # Commented: locale setup

                try:
                    library_module = importlib.import_module(cl.name)
                    library_path = os.path.dirname(library_module.__file__)
                    static_dir = os.path.join(library_path, 'static')

                    # Auto-register static directory if exists
                    if os.path.isdir(static_dir):
                        if static_dir not in settings.STATICFILES_DIRS:
                            settings.STATICFILES_DIRS.append(static_dir)

                    templates_dir = os.path.join(library_path, 'templates')
                    if os.path.isdir(templates_dir):
                        for template_cfg in settings.TEMPLATES:
                            dirs = template_cfg.setdefault('DIRS', [])
                            if templates_dir not in dirs:
                                dirs.append(templates_dir)
                except ImportError:
                    raise ImportError(f'Library "{cl.name}" not found') from None

    def register_app_commands(self, app_name: str, app_path: str):
        """
        Discovers and registers Django management commands from app.
        Scans app's management/commands/ directory for .py files.

        Args:
            app_name: Django app name (dotted path)
            app_path: Filesystem path to app directory

        RAG keywords: management commands, command discovery, django commands
        """
        commands_dir = Path(app_path) / 'management' / 'commands'

        if not commands_dir.exists():
            return

        for command_file in commands_dir.iterdir():
            if (
                command_file.is_file()
                and command_file.suffix == '.py'
                and command_file.stem != '__init__'
            ):
                command_name = command_file.stem
                self.register_command(app_name, command_name)

    def register_command(self, app_name: str, command_name: str):
        """
        Registers single management command if not already registered.

        Args:
            app_name: Django app name containing command
            command_name: Command name (filename without .py)

        RAG keywords: command registration, management command, django
        """
        commands = get_commands()

        if command_name not in commands:
            load_command_class(app_name, command_name)
            commands[command_name] = app_name


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
