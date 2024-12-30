import datetime
import uuid

from decimal import Decimal
from typing import Any, Dict, List, Type, Union, get_origin, get_args
from dataclasses import fields

from django.db import models
from django.db.models.fields.files import FieldFile

from .transports import Transport


class Serializer:
    """Serializador personalizado para transformar modelos em dicionários baseados em transports."""

    def __init__(self, model: models.Model, transport: Type[Transport]):
        self.transport = transport
        self.model = model

    def serialize(self, instance) -> Dict[str, Any]:
        if not isinstance(self.transport, type) or not issubclass(
            self.transport, Transport
        ):
            raise ValueError("O transport deve ser uma subclasse de Transport.")

        if not isinstance(instance, self.model):
            raise ValueError(
                f"Foi passada uma instância do tipo {instance.__class__} em um serializer"
                f" do modelo {self.model}"
            )

        serialized_data = {}

        for field in fields(self.transport):
            field_name = field.name
            field_type = field.type
            value = getattr(instance, field_name, None)
            serialized_data[field_name] = self._serialize_field(value, field_type)

        return serialized_data

    def _serialize_field(self, value: Any, field_type: Any) -> Any:
        """Serializa um campo individual com base no tipo especificado no transporte."""

        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (uuid.UUID, Decimal)):
            return str(value)
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()

        if isinstance(value, FieldFile):
            return value.url if value else None

        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin is list or origin is List:
            return [self._serialize_field(item, args[0]) for item in value]

        if origin is dict or origin is Dict:
            key_type, value_type = args
            return {
                self._serialize_field(k, key_type): self._serialize_field(v, value_type)
                for k, v in value.items()
            }

        if origin is Union:
            for arg in args:
                try:
                    return self._serialize_field(value, arg)
                except Exception:
                    continue

        if issubclass(field_type, Transport):
            return Serializer(model=type(value), transport=field_type).serialize(
                instance=value
            )

        raise TypeError(f"Tipo não suportado: {field_type}")
