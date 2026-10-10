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
Request rate limits of routes: a fixed window counted in the default cache (Redis).

`throttle(rate)` is a FastAPI dependency (`dependencies=[throttle('5/minute')]` of a route
or of an `http_*` decorator). On a route of a route class it counts the requests of the
user of the route (`self.inject.user` of bazis-users) or of the IP address of an anonymous
one; the actions declared `public=True` get `BAZIS_THROTTLE_PUBLIC` per user or IP address unless they
declare their own throttle. Over the limit the request fails with 429 `ERR_THROTTLED` and
the header `Retry-After` (seconds to the next window).

Tags: RAG, EXPORT
"""

import logging
import math
import time
from collections.abc import Callable
from typing import Any

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string

from fastapi import Depends, Request
from fastapi.params import Depends as DependsCls

from bazis.core.errors import JsonApiThrottledException
from bazis.core.utils.rates import parse_rate


logger = logging.getLogger(__name__)


#: what the requests are counted by: the user of the route, else the IP address (default);
#: always the IP address
THROTTLE_KEYS = ('user_or_ip', 'ip')


class Throttle:
    """
    The dependency of `throttle()`. A route class binds it to the user of its route
    (`InitialRouteBase.endpoint_make`); elsewhere it counts by the IP address.

    Tags: RAG
    """

    def __init__(
        self, rate: str | Callable[[], str | None], key: str = 'user_or_ip', scope: str | None = None
    ):
        if key not in THROTTLE_KEYS:
            raise ValueError(f'Invalid throttle key {key!r}: one of {THROTTLE_KEYS}')
        if not callable(rate):
            parse_rate(rate)
        self.rate = rate
        self.key = key
        self.scope = scope

    def __call__(self, request: Request) -> None:
        route = request.scope.get('route')
        self.check(request, scope=getattr(route, 'name', None) or request.url.path)

    def ident(self, request: Request, user: Any = None) -> str:
        """
        Whom the requests are counted for: `user:<pk>` of an authenticated user (key
        `user_or_ip`), else `ip:<address>`.
        """
        if self.key == 'user_or_ip' and user is not None and not user.is_anonymous:
            return f'user:{user.pk}'
        return f'ip:{request.client.host if request.client else "unknown"}'

    def check(self, request: Request, user: Any = None, scope: str | None = None) -> None:
        """
        Counts the request in the window of its scope (the `scope` of the throttle, else
        the route) and fails with 429 over the limit. Nothing is counted with
        `BAZIS_THROTTLE_ENABLED` off, without a rate (the callable returned None or ''), or
        for a request `BAZIS_THROTTLE_EXEMPT` exempts. An invalid rate of a callable (a
        dynamic setting) and a failing cache are logged and let the request through.
        """
        if not settings.BAZIS_THROTTLE_ENABLED:
            return
        rate = self.rate() if callable(self.rate) else self.rate
        if not rate:
            return
        try:
            limit, period = parse_rate(rate)
        except ValueError:
            logger.error('Throttle of %s not applied: %s', self.scope or scope, rate, exc_info=True)
            return
        ident = self.ident(request, user)
        if (exempt := settings.BAZIS_THROTTLE_EXEMPT) and import_string(exempt)(request, ident):
            return

        now = time.time()
        window = int(now // period)
        key = f'bazis:throttle:{self.scope or scope}:{ident}:{period}:{window}'
        try:
            cache.add(key, 0, timeout=period)
            try:
                count = cache.incr(key)
            except ValueError:
                # the window expired between add and incr
                cache.set(key, 1, timeout=period)
                count = 1
        except Exception:
            logger.warning('Throttle of %s not applied: the cache failed', self.scope or scope, exc_info=True)
            return
        if count is not None and count > limit:
            retry_after = max(1, math.ceil((window + 1) * period - now))
            raise JsonApiThrottledException(headers={'Retry-After': str(retry_after)})


def throttle(
    rate: str | Callable[[], str | None], key: str = 'user_or_ip', scope: str | None = None
) -> DependsCls:
    """
    A dependency that limits the requests of a route to `rate` (`'<number>/<period>'`, the
    period second, minute, hour or day; a callable returning one is read per request, e.g.
    a dynamic setting: `lambda: settings.MY_RATE`, None or '' then means no limit) in a
    fixed window: `@http_post('/verify/', public=True, dependencies=[throttle('10/minute')])`.
    `key`: `user_or_ip` counts the user of the route (bazis-users), else the IP address;
    `ip` always the IP address. `scope` shares the count among the routes that name it
    (by default each route counts its own).

    Tags: RAG, EXPORT
    """
    return Depends(Throttle(rate, key=key, scope=scope))


def split_throttles(dependencies) -> tuple[list[Throttle], list]:
    """
    The throttles among the dependencies of a route, and the other dependencies.
    """
    throttles, others = [], []
    for dep in dependencies or ():
        if isinstance(dep, DependsCls) and isinstance(dep.dependency, Throttle):
            throttles.append(dep.dependency)
        else:
            others.append(dep)
    return throttles, others


def public_rate() -> str | None:
    """
    The rate of the actions declared `public=True` without a throttle of their own
    (`BAZIS_THROTTLE_PUBLIC`, a dynamic setting read per request).
    """
    return settings.BAZIS_THROTTLE_PUBLIC


class RateFormField(forms.CharField):
    """
    The admin field of a dynamic rate setting (`BAZIS_THROTTLE_PUBLIC`): a rate or empty.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('required', False)
        super().__init__(**kwargs)

    def validate(self, value):
        super().validate(value)
        if value:
            try:
                parse_rate(value)
            except ValueError as err:
                raise forms.ValidationError(str(err)) from None
