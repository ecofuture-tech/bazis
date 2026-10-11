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

from constance import settings
from constance.backends.database import DatabaseBackend as DatabaseBackendBase


class DatabaseBackend(DatabaseBackendBase):
    """
    The constance backend of Bazis (`CONSTANCE_BACKEND`): the database backend of
    constance that does not save the default of a setting without a saved value.
    Constance saves the default on its first read (also by the admin page and `manage.py
    constance get`), and the default of a dynamic setting is its `BS_*` variable: a later
    change of the variable then had no effect. A dynamic setting follows its `BS_*`
    variable until a value is set (the admin, `manage.py constance set`, `config.X = ...`).
    """

    def set(self, key, value):
        if value == settings.CONFIG[key][0] and not self._saved(key):
            return
        super().set(key, value)

    def _saved(self, key) -> bool:
        return self._model._default_manager.filter(key=self.add_prefix(key)).exists()
