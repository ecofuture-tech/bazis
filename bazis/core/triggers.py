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

from typing import TYPE_CHECKING

from django.db import connection

from pydantic import BaseModel

import pgtrigger

from bazis.core.utils.model_meta import RelationInfo
from bazis.core.utils.triggers import trigger_name


if TYPE_CHECKING:
    from .models_abstract import InitialBase


class TriggerSetDtCreate(pgtrigger.Trigger):
    """
    Trigger to set the dt_created and dt_updated fields to the current timestamp
    before inserting a new record.

    Tags: RAG, EXPORT
    """

    name = 'set_dt_created'
    when = pgtrigger.Before
    operation = pgtrigger.Insert
    func = """
        NEW.dt_created = STATEMENT_TIMESTAMP();
        NEW.dt_updated = STATEMENT_TIMESTAMP();
        RETURN NEW;
    """


class TriggerSetDtUpdate(pgtrigger.Trigger):
    """
    Trigger to set the dt_updated field to the current timestamp before updating a
    record. Ensures dt_created is set if it is null.

    Tags: RAG, EXPORT
    """

    name = 'set_dt_update'
    when = pgtrigger.Before
    operation = pgtrigger.Update
    func = """
        IF OLD.dt_created IS NULL THEN
            NEW.dt_created = STATEMENT_TIMESTAMP();
        END IF;
        IF NEW.dt_created IS NULL THEN
            NEW.dt_created = OLD.dt_created;
        END IF;
        NEW.dt_updated = STATEMENT_TIMESTAMP();
        RETURN NEW;
    """


class FieldTransferSchema(BaseModel):
    """
    Schema for defining field transfer configurations.

    Attributes:
        source (str): The source field from which the value is transferred.
        only_for_unset (bool): If True, transfer the value only if the target field is unset.
            Defaults to False.

    Tags: RAG, EXPORT
    """

    source: str
    only_for_unset: bool = False


class FieldsTransferTrigger(pgtrigger.Trigger):
    """
    Trigger to transfer values from a source object to the current object.
    Note: The current implementation has limitations:

    - Data transfer only works when saving the object on which the trigger is attached.
    - m2m relationships are not supported.
    - Data transfer is not supported when updating the source object.
    - In the presence of feedback, data is not transferred without changing the current object.

    TODO: Consider rewriting for a more flexible implementation in the future.

    Tags: RAG, EXPORT
    """

    tpl_name = 'f_transfer'
    when = pgtrigger.Before
    operation = pgtrigger.Insert | pgtrigger.Update

    def __init__(
        self,
        name=None,
        related_field: str = None,
        fields: dict[str, FieldTransferSchema] = None,
        **kwargs,
    ):
        """
        Initializes the FieldsTransferTrigger with the specified parameters.

        Args:
            name (str, optional): The name of the trigger. Defaults to None.
            related_field (str, optional): The related field for which the trigger is defined.
                Defaults to None.
            fields (dict[str, FieldTransferSchema], optional): A dictionary mapping target fields
                to their transfer configurations. Defaults to None.
        """
        fields_keys = '_'.join(sorted(fields.keys()))
        self.name = trigger_name(name or f'{self.tpl_name}_{related_field}_{fields_keys}')
        self.related_field_name = related_field
        self.fields = fields
        self.sources_to_tmp = {}
        self.sources_to_columns = {}
        super().__init__(name=self.name)

    def get_related_field(self, model: type['InitialBase'] = None) -> RelationInfo:
        """
        Retrieves the RelationInfo object for the related field in the given model.

        Args:
            model (Type['InitialBase'], optional): The model to retrieve the related field from. Defaults to None.

        Returns:
            RelationInfo: Information about the related field.

        Raises:
            ValueError: If the related field is not found in the model.
        """
        if related_field := model.get_fields_info().relations.get(self.related_field_name):
            return related_field
        raise ValueError(f'Could not find field {self.related_field_name} in model {model}')

    def get_declare(self, model: type['InitialBase']):
        """
        Generates the declaration part of the trigger function, including temporary variables and their types.

        Args:
            model (Type['InitialBase']): The model for which the trigger is being generated.

        Returns:
            list[tuple[str, str]]: A list of tuples containing temporary variable names and their database types.
        """
        model = self._primary_model
        SourceModel: type[InitialBase] = self.get_related_field(model).related_model  # noqa: N806

        self.sources_to_columns = {
            f_conf.source: model_field.column
            for f_conf in self.fields.values()
            if (model_field := SourceModel.get_fields_info().fields[f_conf.source].model_field)
        }

        self.sources_to_tmp = {
            f_source: f'_{f_column}' for f_source, f_column in self.sources_to_columns.items()
        }

        return [
            (f_tmp, model_field.db_type(connection))
            for f_name, f_tmp in self.sources_to_tmp.items()
            if (model_field := SourceModel.get_fields_info().fields[f_name].model_field)
        ]

    def get_func(self, model: type['InitialBase']):
        """
        Generates the trigger function for transferring values from the source object to the current object.

        Args:
            model (Type['InitialBase']): The model for which the trigger is being generated.

        Returns:
            str: The trigger function as a string.
        """
        model = self._primary_model
        related_field = self.get_related_field(model)
        RelatedModel = related_field.related_model  # noqa: N806
        model_fields = model.get_fields_info().fields
        # Getting table names from models
        related_table_name = RelatedModel._meta.db_table

        # collecting data for update
        vars_reinstall = ''
        for f_target, f_conf in self.fields.items():
            if f_target not in model_fields:
                continue

            column = model_fields[f_target].model_field.column

            new_update = f'NEW.{column} := {self.sources_to_tmp[f_conf.source]};\n'

            if f_conf.only_for_unset:
                vars_reinstall += f"""
                    IF (TG_OP = 'INSERT') OR (OLD.{column} IS NULL) THEN
                        {new_update}
                    END IF;
                """
            else:
                vars_reinstall += new_update

        if related_field.is_m2m:
            # Getting the name of the related field from related_name
            through_model = related_field.through_model
            through_table_name = through_model._meta.db_table
            dest_field_name = through_model._meta.get_field(model._meta.model_name).column
            related_field_name = through_model._meta.get_field(RelatedModel._meta.model_name).column

            return f"""
                    SELECT {', '.join(self.sources_to_columns.values())}
                    INTO {', '.join(self.sources_to_tmp.values())}
                    FROM {related_table_name} s
                    JOIN {through_table_name} th ON s.id = th.{related_field_name}
                    WHERE th.{dest_field_name} = NEW.{model._meta.pk.column}
                    LIMIT 1;

                    IF FOUND THEN
                        {vars_reinstall}
                    END IF;

                RETURN NEW;
            """
        elif related_field.reverse:
            fk_field_name = RelatedModel._meta.get_field(model._meta.model_name.lower()).column

            return f"""
                    SELECT {', '.join(self.sources_to_columns.values())}
                    INTO {', '.join(self.sources_to_tmp.values())}
                    FROM {related_table_name} r
                    WHERE r.{fk_field_name} = NEW.{model._meta.pk.column}
                    LIMIT 1;

                    IF FOUND THEN
                        {vars_reinstall}
                    END IF;

                RETURN NEW;
            """
        else:
            related_field_id = related_field.model_field.column

            return f"""
                    SELECT {', '.join(self.sources_to_columns.values())}
                        INTO {', '.join(self.sources_to_tmp.values())}
                        FROM {RelatedModel._meta.db_table} r
                        WHERE r.{model._meta.pk.column} = NEW.{related_field_id}
                        LIMIT 1;

                    IF FOUND THEN
                        {vars_reinstall}
                    END IF;

                RETURN NEW;
            """
