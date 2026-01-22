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
