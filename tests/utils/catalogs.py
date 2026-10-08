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

import array
import struct


def write_mo(path, messages: dict[str, str]) -> None:
    """
    Writes a compiled gettext catalog (the format of `msgfmt`, which CI may not have).
    """
    messages = {'': 'Content-Type: text/plain; charset=UTF-8\n', **messages}
    keys = sorted(messages)
    ids = strs = b''
    offsets = []
    for key in keys:
        key_bytes, value_bytes = key.encode(), messages[key].encode()
        offsets.append((len(ids), len(key_bytes), len(strs), len(value_bytes)))
        ids += key_bytes + b'\0'
        strs += value_bytes + b'\0'
    keys_start = 7 * 4 + 16 * len(keys)
    values_start = keys_start + len(ids)
    key_offsets, value_offsets = [], []
    for id_offset, id_len, str_offset, str_len in offsets:
        key_offsets += [id_len, id_offset + keys_start]
        value_offsets += [str_len, str_offset + values_start]
    path.parent.mkdir(parents=True)
    path.write_bytes(
        struct.pack('Iiiiiii', 0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + len(keys) * 8, 0, 0)
        + array.array('i', key_offsets + value_offsets).tobytes()
        + ids
        + strs
    )
