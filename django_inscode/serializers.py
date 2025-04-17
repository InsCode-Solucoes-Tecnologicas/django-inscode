from dataclasses import fields, is_dataclass
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
    Protocol,
    Type,
)
from decimal import Decimal
from uuid import UUID

from django.db import models
from django.core.files.base import File

from marshmallow import Schema

from .transports import Transport

import datetime

SerializedData = Dict[str, Any]


class SerializerInterface(Protocol):
    def serialize(self, obj: Any) -> SerializedData: ...


class MarshmallowSerializerAdapter(SerializerInterface):
    """
    Adaptador do serializador do marshmallow para a interface de SerializerInterface.
    """

    def __init__(self, schema_class: Type[Schema]):
        self.schema_class = schema_class

    def serialize(self, obj: Schema):
        return self.schema_class().dump(obj)


class Serializer(SerializerInterface):
    """
    Serializador personalizado para transformar instâncias de modelos Django em dicionários.

    Este serializador utiliza um `Transport` para definir os campos e tipos que devem ser
    serializados a partir de uma instância do modelo associado.

    Attributes:
        model (Model): O modelo Django associado ao serializador.
        transport (Type[Transport]): Classe de transporte que define os campos e tipos para serialização.
    """

    def __init__(self, model: models.Model, transport: Type[Transport]):
        """
        Inicializa o serializador com o modelo e o transporte especificados.

        Args:
            model (Model): O modelo Django que será serializado.
            transport (Type[Transport]): Classe de transporte que define os campos e tipos para serialização.

        Raises:
            ValueError: Se `transport` não for uma subclasse de `Transport`.
        """
        if not is_dataclass(transport):
            raise ValueError("O transport deve ser um dataclass.")

        self.model = model
        self.transport = transport

    def serialize(self, instance) -> Dict[str, Any]:
        """
        Serializa uma instância do modelo em um dicionário com base no transporte.

        Args:
            instance (Model): Instância do modelo a ser serializada.

        Returns:
            Dict[str, Any]: Dicionário contendo os dados serializados da instância.

        Raises:
            ValueError: Se o transporte não for uma subclasse de `Transport` ou se a instância não for do tipo esperado.
        """
        if not isinstance(instance, self.model):
            raise ValueError(
                f"Foi passada uma instância do tipo {instance.__class__} em um serializer"
                f" do modelo {self.model}"
            )

        serialized_data = {}

        for field in fields(self.transport):
            field_name = field.name
            field_type = field.type

            value = self._get_field_value(instance, field_name)
            serialized_data[field_name] = self._serialize(value, field_type)

        return serialized_data

    def _get_field_value(self, instance: models.Model, field_name: str) -> Any:
        """Obtém o valor de um campo."""
        field = instance._meta.get_field(field_name)
        if field.many_to_many or field.one_to_many:
            return list(getattr(instance, field_name).all())
        return getattr(instance, field_name, None)

    def _serialize(self, value: Any, field_type: Any) -> Any:
        """Centraliza a lógica de serialização delegando para métodos específicos."""
        if value is None:
            return None

        type_serializers = {
            str: self._serialize_basic,
            int: self._serialize_basic,
            float: self._serialize_basic,
            bool: self._serialize_basic,
            Decimal: self._serialize_decimal,
            UUID: self._serialize_uuid,
            datetime.date: self._serialize_date,
            datetime.datetime: self._serialize_date,
            File: self._serialize_file,
        }

        for base_type, serializer_func in type_serializers.items():
            if isinstance(value, base_type):
                return serializer_func(value)

        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin in [list, List]:
            return self._serialize_list(value, args[0])

        if origin in [dict, Dict]:
            return self._serialize_dict(value, args)

        if origin is Union and type(None) in args:
            non_none_type = next(arg for arg in args if arg is not type(None))
            return self._serialize(value, non_none_type)

        if is_dataclass(field_type):
            return self._serialize_transport(value, field_type)

        raise TypeError(f"Tipo não suportado: {field_type}")

    def _serialize_basic(self, value: Any) -> Any:
        """Serializa tipos básicos como str, int e bool."""
        return value

    def _serialize_decimal(self, value: Decimal) -> str:
        """Serializa valores Decimais como strings."""
        return str(value)

    def _serialize_uuid(self, value: UUID) -> str:
        """Serializa UUIDs como strings."""
        return str(value)

    def _serialize_date(self, value: Union[datetime.date, datetime.datetime]) -> str:
        """Serializa datas e datetimes como strings ISO 8601."""
        return value.isoformat()

    def _serialize_file(self, value: File) -> Optional[str]:
        """Serializa arquivos como URLs."""
        return value.url if value else None

    def _serialize_list(self, value: List[Any], item_type: Any) -> List[Any]:
        """Serializa listas recursivamente."""
        return [self._serialize(item, item_type) for item in value]

    def _serialize_dict(self, value: Dict[Any, Any], types: tuple) -> Dict[Any, Any]:
        """Serializa dicionários recursivamente."""
        key_type, value_type = types
        return {
            self._serialize(k, key_type): self._serialize(v, value_type)
            for k, v in value.items()
        }

    def _serialize_transport(
        self, value: models.Model, transport_type: Any
    ) -> Dict[str, Any]:
        """Serializa objetos relacionados usando transportes aninhados."""
        model_class = type(value)
        return Serializer(model=model_class, transport=transport_type).serialize(value)


class SerializerFactory:
    @staticmethod
    def get_serializer(serializer):
        if isinstance(serializer, type) and issubclass(serializer, Schema):
            return MarshmallowSerializerAdapter(serializer)

        if isinstance(serializer, object) and isinstance(serializer, Serializer):
            return serializer

        raise TypeError(
            f"Tipo de serializador não suportado: {type(serializer).__name__}"
        )


__all__ = [
    "SerializerInterface",
    "MarshmallowSerializerAdapter",
    "Serializer",
    "SerializerFactory",
]
