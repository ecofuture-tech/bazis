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

from constance.base import Config as ConfigBase


class Config(ConfigBase):
    """
    A class that extends the base configuration class from constance, providing
    custom attribute setting behavior.
    """

    def __setattr__(self, key, value):
        """
        Overrides the default __setattr__ method to set attributes on the configuration
        object, with exception handling to silently pass any errors.
        """
        try:
            super().__setattr__(key, value)
        except Exception:
            pass
