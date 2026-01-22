import os

from django.core.files.base import ContentFile


def build_content_file(file_path):
    with open(file_path, 'rb') as file:
        return ContentFile(file.read(), name=os.path.basename(file_path))
