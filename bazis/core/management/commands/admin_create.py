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
