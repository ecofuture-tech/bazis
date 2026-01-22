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

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    This Django management command creates an admin user non-interactively if it
    doesn't already exist.

    Tags: RAG
    """

    help = "Creates an admin user non-interactively if it doesn't exist"

    def handle(self, *args, **options):
        """
        Executes the command to create an admin user by fetching the username and
        password from environment variables and creating the user if it does not exist.
        """
        username = os.getenv('BS_ADMIN_NAME')
        password = os.getenv('BS_ADMIN_PASSWORD')

        User = get_user_model()  # noqa: N806
        # find the user
        user = User.objects.filter(username=username).first()
        if not user:
            User.objects.create_superuser(username=username, password=password, email='')
