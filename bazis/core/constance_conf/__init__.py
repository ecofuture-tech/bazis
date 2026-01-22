from django.utils.functional import LazyObject


class LazyConfig(LazyObject):
    """
    A lazily-initialized configuration object that defers the creation of the actual
    configuration until it is accessed.
    """

    def _setup(self):
        """
        Initializes the LazyConfig object by importing and setting up the actual Config
        instance.
        """
        from .base import Config

        self._wrapped = Config()


config = LazyConfig()
