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

import logging


logger = logging.getLogger(__name__)


def force_global_logging_level(target_level=logging.INFO, block_higher_levels=True):
    """
    Forcibly sets logging level for ALL loggers in the system

    Args:
        target_level: Target level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL or string)
        block_higher_levels: Whether to block attempts to set higher levels

    Tags: RAG, EXPORT
    """

    # Convert string to number if needed
    if isinstance(target_level, str):
        target_level = getattr(logging, target_level.upper(), logging.INFO)

    level_name = logging.getLevelName(target_level)

    def apply_level_to_all():
        # 1. Root logger
        logging.getLogger().setLevel(target_level)

        # 2. ALL existing named loggers
        count = 0
        for name in list(logging.Logger.manager.loggerDict.keys()):
            logger = logging.getLogger(name)
            logger.setLevel(target_level)
            count += 1

        return count

    # Apply to all existing loggers
    existing_count = apply_level_to_all()

    # 3. INTERCEPT creation of new loggers
    original_getLogger = logging.getLogger  # noqa: N806

    def patched_getLogger(name=None):  # noqa: N802
        logger = original_getLogger(name)
        logger.setLevel(target_level)  # Force our level for ALL new loggers
        return logger

    logging.getLogger = patched_getLogger

    # 4. OPTIONALLY block setting higher levels
    if block_higher_levels:
        original_setLevel = logging.Logger.setLevel  # noqa: N806

        def controlled_setLevel(self, level):  # noqa: N802
            # Convert to number if string
            if isinstance(level, str):
                numeric_level = getattr(logging, level.upper(), target_level)
            else:
                numeric_level = level

            # If trying to set level higher than target - block it
            if numeric_level > target_level:
                logger.debug(
                    f"🚫 BLOCKING setLevel({logging.getLevelName(numeric_level)}) for '{self.name}', keeping {level_name}"
                )
                numeric_level = target_level

            return original_setLevel(self, numeric_level)

        logging.Logger.setLevel = controlled_setLevel
        block_msg = f' with blocking levels above {level_name}'
    else:
        block_msg = ''

    logger.debug(f'✅ SET {level_name} for ALL {existing_count + 1} loggers{block_msg}')
