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

def include_to_list(include: str = None) -> list:
    """
    Converts a comma-separated string into a list of stripped, non-empty items. If
    the input string is None or empty, returns an empty list.

    Tags: RAG, EXPORT
    """
    if not include:
        return []
    return [it.strip() for it in include.split(',') if it.strip()]
