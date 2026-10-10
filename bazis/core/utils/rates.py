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
The rates of the request rate limits (`bazis.core.throttle`), without dependencies: the
settings validate them when they load.
"""

#: seconds of the periods of a rate (`'<number>/<period>'`)
RATE_PERIODS = {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400}


def parse_rate(rate: str) -> tuple[int, int]:
    """
    The number of requests and the seconds of the window of a rate `'<number>/<period>'`,
    the period second, minute, hour or day (or its first letter): `'30/minute'`, `'5/s'`.
    """
    try:
        number, period = rate.split('/')
        seconds = next(
            sec for name, sec in RATE_PERIODS.items() if period.strip() in (name, name[0])
        )
        limit = int(number)
    except (AttributeError, ValueError, StopIteration):
        raise ValueError(
            f'Invalid throttle rate {rate!r}: expected "<number>/<second|minute|hour|day>"'
        ) from None
    if limit < 1:
        raise ValueError(f'Invalid throttle rate {rate!r}: the number must be positive')
    return limit, seconds
