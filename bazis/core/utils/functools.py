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

import dataclasses
import hashlib
import inspect
import json
import pickle
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal
from threading import Lock
from time import time
from types import TracebackType
from typing import Any, Type  # noqa: UP035

from django.utils.text import camel_case_to_spaces


def get_attr(obj, path, default=None):
    """
    Retrieves nested attribute from object using dot/double-underscore path.

    Supports traversal through:
    - Object attributes (getattr)
    - Dictionary keys
    - List indices

    Args:
        obj: Object to traverse
        path: Dot-separated path (e.g., 'user.profile.name' or 'user__profile__name')
        default: Fallback value if path fails

    Examples:
        get_attr(obj, 'user.profile.age', 0)
        get_attr(data, 'items.0.name', 'Unknown')

    Tags: RAG, EXPORT
    """
    if isinstance(path, str):
        # Normalize Django-style __ to dots
        path = path.replace('__', '.').split('.')
    if not isinstance(path, Iterable):
        path = [path]
    try:
        for p in path:
            if isinstance(obj, list):
                obj = obj[int(p)]
            elif isinstance(obj, dict):
                obj = obj[p]
            else:
                obj = getattr(obj, p)
    except Exception:
        obj = default
    if obj is None:
        obj = default
    return obj


def snake_2_camel(s):
    """
    Converts snake_case to CamelCase.
    Example: 'user_profile' -> 'UserProfile'

    Tags: RAG, EXPORT
    """
    return ''.join(x.title() for x in s.split('_'))


def camel_2_snake(s):
    """
    Converts CamelCase to snake_case using Django's utility.
    Example: 'UserProfile' -> 'user_profile'

    Tags: RAG, EXPORT
    """
    return camel_case_to_spaces(s).replace(' ', '_')


def dict_reversing(source):
    """
    Reverses dictionary mapping: values become keys, original keys aggregated in lists.

    Example:
        {'a': 1, 'b': 1, 'c': 2} -> {1: ['a', 'b'], 2: ['c']}

    Tags: RAG, EXPORT
    """
    dest = defaultdict(list)
    {dest[v].append(k) for k, v in source.items()}
    return dict(dest)


def cast_types(value, target_type):
    """
    Safe type casting with fallback to original value on failure.

    Args:
        value: Value to cast
        target_type: Target type class (int, str, Decimal, etc.)

    Returns original value if casting raises TypeError or ValueError.

    Tags: RAG, EXPORT
    """
    rs = value
    try:
        rs = target_type(value)
    except (TypeError, ValueError):
        pass
    return rs


def sys_uncache(exclude):
    """
    Removes modules from sys.modules cache for hot reload.
    Excludes specified packages from removal.

    Used for development auto-reload functionality.
    Source: https://medium.com/@chipiga86/python-monkey-patching-like-a-boss-87d7ddb8098e

    Args:
        exclude: Iterable of module paths to preserve (e.g., ['django', 'bazis'])

    Tags: RAG, EXPORT
    """
    pkgs = []
    for mod in exclude:
        pkg = mod.split('.', 1)[0]
        pkgs.append(pkg)

    to_uncache = []
    for mod in sys.modules:
        if mod in exclude:
            continue

        if mod in pkgs:
            to_uncache.append(mod)
            continue

        for pkg in pkgs:
            if mod.startswith(pkg + '.'):
                to_uncache.append(mod)
                break

    for mod in to_uncache:
        del sys.modules[mod]


def get_class_name_from_method(meth):
    """
    Extracts class name from method's __qualname__.
    Handles nested classes and local functions.

    Tags: RAG, EXPORT
    """
    return meth.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0]


def get_class_name(entity) -> str:
    """
    Returns fully qualified class name (module.Class).
    Works for classes and instances.

    Example: 'bazis.core.models.User'

    Tags: RAG, EXPORT
    """
    if hasattr(entity, '__qualname__'):
        return f'{entity.__module__}.{entity.__qualname__}'
    return f'{entity.__class__.__module__}.{entity.__class__.__qualname__}'


def get_class_from_method(meth):
    """
    Determines the class that defines a given method.
    Handles bound methods, functions, and descriptors.

    Source: https://stackoverflow.com/a/25959545

    Args:
        meth: Method or function to inspect

    Returns:
        Class that defined the method, or None

    Tags: RAG, EXPORT
    """
    if inspect.ismethod(meth):
        for cls in inspect.getmro(meth.__self__.__class__):
            if cls.__dict__.get(meth.__name__) is meth:
                return cls
        meth = meth.__func__  # fallback to __qualname__ parsing
    if inspect.isfunction(meth):
        cls = getattr(inspect.getmodule(meth), get_class_name_from_method(meth))
        if isinstance(cls, type):
            return cls
    return getattr(meth, '__objclass__', None)  # handle special descriptor objects


def get_func_sig_param(func: Callable, param_name: str) -> inspect.Parameter:
    """
    Retrieves specific parameter from function signature.

    Tags: RAG, EXPORT
    """
    return inspect.signature(func).parameters.get(param_name)


def func_sig_params_append(func: Callable, *params: inspect.Parameter):
    """
    Appends parameters to function signature, replacing duplicates.
    Excludes *args and **kwargs from original signature.

    Used for dynamic signature modification in decorators.

    Tags: RAG, EXPORT
    """
    sig = inspect.signature(func)
    # New parameters take priority
    params_names = {p.name for p in params}
    parameters = [
        p
        for p in sig.parameters.values()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and p.name not in params_names
    ]
    sig = sig.replace(parameters=parameters + list(params))
    func.__signature__ = sig


def func_sig_param_replace(func: Callable, param_name: str, default=None, annotation=None):
    """
    Replaces default value or annotation of specific parameter in signature.

    Tags: RAG, EXPORT
    """
    sig = inspect.signature(func)
    parameters = []
    for p in sig.parameters.values():
        if p.name == param_name:
            parameters.append(
                inspect.Parameter(
                    name=p.name,
                    kind=p.kind,
                    default=default or p.default,
                    annotation=annotation or p.annotation,
                )
            )
        else:
            parameters.append(p)
    sig = sig.replace(parameters=parameters)
    func.__signature__ = sig


def func_sig_transfer(src: Callable, dst: Callable):
    """
    Transfers complete signature from source to destination function.
    Used in wrapper functions to preserve original signature.

    Tags: RAG, EXPORT
    """
    dst_sig = inspect.signature(dst)
    dst_sig = dst_sig.replace(parameters=list(inspect.signature(src).parameters.values()))
    dst.__signature__ = dst_sig


def inheritors(klass):
    """
    Returns all subclasses recursively (entire inheritance tree).

    Tags: RAG, EXPORT
    """
    subclasses = set()
    klasses = [klass]
    while klasses:
        parent = klasses.pop()
        for child in parent.__subclasses__():
            if child not in subclasses:
                subclasses.add(child)
                klasses.append(child)
    return subclasses


@dataclasses.dataclass
class ExcInterceptError:
    """
    Container for intercepted exception details.
    Stores type, value, and traceback of caught exception.
    """

    type: Type[Exception] = None  # noqa: UP006
    value: Exception = None
    traceback: TracebackType = None


class ExcIntercept:
    """
    Context manager for exception interception without raising.
    Captures exception details in error attribute.

    Usage:
        with ExcIntercept(ValueError) as err:
            risky_operation()
        if err.value:
            handle_error(err)

    Tags: RAG, EXPORT
    """

    def __init__(self, exc_class: type[Exception] = None):
        """
        Args:
            exc_class: Exception type to intercept (None = all exceptions)
        """
        self.exc_class = exc_class
        self.error = ExcInterceptError()

    def __enter__(self):
        """Returns error container for exception details."""
        return self.error

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Captures exception if it matches exc_class.
        Returns True to suppress exception propagation.
        """
        if exc_type and (
            (self.exc_class and issubclass(exc_type, self.exc_class)) or not self.exc_class
        ):
            self.error.type = exc_type
            self.error.value = exc_val
            self.error.traceback = exc_tb
            return True


class ClassLookupDict:
    """
    Dictionary with class inheritance-aware lookups.
    Used for Django field to Pydantic type mapping (TYPES_DJANGO_TO_SCHEMA_LOOKUP).

    Traverses MRO (Method Resolution Order) to find matching superclass.
    Example: IntegerField lookup finds django_models.Field if no exact match.

    Tags: RAG, EXPORT
    """

    def __init__(self, mapping):
        """
        Args:
            mapping: Dict mapping class types to values
        """
        self.mapping = mapping

    def __getitem__(self, key):
        """
        Looks up value by class type, checking inheritance hierarchy.
        Supports _proxy_class attribute for proxy objects (e.g., BoundField).
        """
        if hasattr(key, '_proxy_class'):
            # Handle proxy classes (e.g., BoundField acts as Field)
            base_class = key._proxy_class
        else:
            base_class = key.__class__

        for cls in inspect.getmro(base_class):
            if cls in self.mapping:
                return self.mapping[cls]
        raise KeyError(f'Class {base_class.__name__} not found in lookup.')

    def __setitem__(self, key, value):
        """Adds or updates mapping for a class."""
        self.mapping[key] = value


class CtxToggle:
    """
    Simple boolean flag context manager.
    Flag is False inside context, True outside.

    Tags: RAG, EXPORT
    """

    def __init__(self):
        """Initializes with flag=True."""
        self.allow = True

    def __enter__(self):
        """Sets flag to False."""
        self.allow = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Resets flag to True."""
        self.allow = True


def throttle(seconds: int = 1, first_run=True):
    """
    Decorator to rate-limit function execution.

    Args:
        seconds: Minimum interval between calls
        first_run: If True, first call executes immediately

    Example:
        @throttle(seconds=5)
        def expensive_operation():
            ...

    Tags: RAG, EXPORT
    """

    def decor(func):
        """Decorator wrapper with throttling state."""
        last_run: float | None = None if first_run else time()

        def wrap(*args, **kwargs):
            """Enforces minimum interval between executions."""
            nonlocal last_run
            if not last_run or (last_run + seconds) < time():
                response = func(*args, **kwargs)
                last_run = time()
                return response

        return wrap

    return decor


def uniq_id(obj: Any) -> str:
    try:
        data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        return hashlib.md5(data).hexdigest()
    except (pickle.PicklingError, TypeError, AttributeError):
        return hashlib.md5(repr(obj).encode('utf-8')).hexdigest()


# def uniq_id(value) -> str:
#     """
#     Generates MD5 hash as unique identifier.
#
#     Supports:
#     - Strings: hashed directly
#     - Iterables: recursive hash of elements
#     - Callables: uses fully qualified name
#     - Others: str() conversion
#
#     Tags: RAG, EXPORT
#     """
#     print('uniq_id:', value, type(value))
#     if isinstance(value, str):
#         data = value
#     elif isinstance(value, Iterable):
#         data = ':::'.join([uniq_id(v) for v in value])
#     elif callable(value) and (hasattr(value, '__class__') or hasattr(value, '__qualname__')):
#         data = get_class_name(value)
#     else:
#         data = str(value)
#
#     if data:
#         return md5(data.encode()).hexdigest()


def price_4217_to_decimal(value: int, exp: int, rounding_type=None) -> Decimal:
    """
    Converts ISO 4217 price integer to Decimal with specified decimal places.

    ISO 4217: Currency amounts stored as integers with exponent.
    Example: $12.34 stored as 1234 with exp=2

    Args:
        value: Integer amount
        exp: Decimal places (exponent)
        rounding_type: Decimal rounding mode (defaults to BAZIS_DECIMAL_HALF)

    Returns: Decimal with proper precision

    Tags: RAG, EXPORT
    """
    from django.conf import settings

    rounding_type = rounding_type or settings.BAZIS_DECIMAL_HALF
    factor = Decimal(10**exp)
    return Decimal(value).quantize(Decimal('1.' + '0' * exp), rounding=rounding_type) / factor


def decimal_to_price_4217(value: Decimal, exp: int = 0) -> int:
    """
    Converts Decimal to ISO 4217 integer format.

    Args:
        value: Decimal amount
        exp: Decimal places (exponent)

    Returns: Integer representation

    Example: Decimal('12.34') with exp=2 -> 1234

    Tags: RAG, EXPORT
    """
    multiplier = 10**exp
    return int(value * multiplier + Decimal('0.5'))


def join_url_parts(*parts):
    """
    Joins URL segments with proper slash handling.
    Strips leading/trailing slashes from each part before joining.

    Example: join_url_parts('/api/', '/users/', 'profile/') -> 'api/users/profile'

    Tags: RAG, EXPORT
    """
    return '/'.join(str(part).strip('/') for part in parts)


class _SingletonWrapper:
    """
    Internal singleton wrapper for @singleton decorator.
    Maintains single instance per decorated class.
    """

    def __init__(self, cls):
        """Stores wrapped class."""
        self.__wrapped__ = cls
        self._instance = None

    def __call__(self, *args, **kwargs):
        """Returns singleton instance, creating if needed."""
        if self._instance is None:
            self._instance = self.__wrapped__(*args, **kwargs)
        return self._instance


def singleton(cls):
    """
    Singleton decorator ensuring single instance per class.
    Access original class via __wrapped__ attribute.

    Example:
        @singleton
        class Config:
            ...

    Tags: RAG, EXPORT
    """
    return _SingletonWrapper(cls)


class SingletonMixin:
    """
    Thread-safe singleton mixin using __new__ pattern.
    Override _init_singleton() for initialization logic.

    Usage:
        class MyClass(SingletonMixin):
            def _init_singleton(self):
                self.value = 0

    Tags: RAG, EXPORT
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        """Override for singleton initialization logic."""
        pass


class class_or_instance_method:  # noqa: N801
    """
    Descriptor for methods callable on both class and instance.
    First argument is class when called on class, instance when called on instance.

    Usage:
        class MyClass:
            @class_or_instance_method
            def method(self_or_cls):
                if isinstance(self_or_cls, type):
                    # Called on class
                else:
                    # Called on instance

    Tags: RAG, EXPORT
    """

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            # Called through class
            return lambda *args, **kwargs: self.func(owner, *args, **kwargs)
        else:
            # Called through instance
            return lambda *args, **kwargs: self.func(instance, *args, **kwargs)


def json_pretty_print(json_obj, pass_fields: list = None, default_deserializator=str):
    """
    Pretty-prints JSON with human-readable formatting.

    Args:
        json_obj: Object to serialize
        pass_fields: Top-level dict keys to exclude from output
        default_deserializator: Fallback serializer for non-JSON types

    Features:
    - Sorted keys
    - 2-space indentation
    - UTF-8 support (ensure_ascii=False)
    - Custom serializer for unknown types

    Tags: RAG, EXPORT
    """
    if pass_fields and isinstance(json_obj, dict):
        new_json_obj = {k: v for k, v in json_obj.copy().items() if k not in pass_fields}
        return json.dumps(
            new_json_obj,
            sort_keys=True,
            indent=2,
            separators=(',', ': '),
            ensure_ascii=False,
            default=default_deserializator,
        )
    return json.dumps(
        json_obj,
        sort_keys=True,
        indent=2,
        separators=(',', ': '),
        ensure_ascii=False,
        default=default_deserializator,
    )
