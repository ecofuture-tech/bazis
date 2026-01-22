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

"""
The project is a framework for rapid API assembly.
Currently, the project is a hybrid of Django and FastAPI.
Django forms the basis of the ORM and admin panel, while FastAPI forms the basis of the API.

Structure of **bazis**:

- **core**: the root application defining basic mixins and abstractions for using the engine
- **contrib**: a collection of target applications implementing specific functionality

==============================

Approximate structure of each application (all files are optional):

- **models_abstract.py**: mixins or abstractions for creating real models
- **admin_abstract.py**: mixins for creating admin classes
- **routes_abstract.py**: mixins and base classes for assembling class-based routes
- **models.py**: real models required for the application to work
- **admin.py**: application admin classes
- **routes.py**: application route classes
- **router.py**: describes the application's URL routing
- **schemas.py**: static Pydantic schemas used in the module
- **triggers.py**: the framework actively uses the functionality of django-pgtrigger. This module defines the triggers required for the package
- **services/services.py**: dependency services connected in the routing

==============================

Features of bazis models:

- each model and each mixin must inherit from bazis.core.models_abstract.InitialBase
- the logic of the default behavior of the missing Meta class in the model has been changed:
        - according to Django behavior, if a model does not define a Meta class, Django assumes that Meta parameters are not set
        - bazis adds the functionality of default inheritance from all parent classes,
                - i.e., if the Meta class is not defined, the model will receive a composite Meta class from all parents, in the order of inheritance of the model itself.
"""

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version('bazis')
except PackageNotFoundError:
    __version__ = 'dev'
