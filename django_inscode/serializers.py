import datetime
import uuid

from decimal import Decimal
from typing import Any, Dict, List, Type, Union, get_origin, get_args
from dataclasses import fields

from django.db import models
from django.db.models.fields.files import FieldFile
from django.db.models.fields.related import RelatedField
from django.db.models.fields.reverse_related import ForeignObjectRel

from .transports import Transport


class Serializer:
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
        self.transport = transport
        self.model = model

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

            value = getattr(instance, field_name, None)
            serialized_data[field_name] = self._serialize_field(value, field_type)

        for related_field in instance._meta.get_fields():
            if isinstance(related_field, ForeignObjectRel):
                related_name = related_field.get_accessor_name()
                related_manager = getattr(instance, related_name)
                serialized_data[related_name] = [
                    Serializer(
                        model=rel_instance.__class__, transport=self.transport
                    ).serialize(rel_instance)
                    for rel_instance in related_manager.all()
                ]

            elif isinstance(related_field, RelatedField):
                related_name = related_field.name
                value = getattr(instance, related_name, None)
                if value is not None:
                    serialized_data[related_name] = self._serialize_field(
                        value, type(value)
                    )

        return serialized_data

    def _serialize_field(self, value: Any, field_type: Any) -> Any:
        """
        Serializa um campo individual com base no tipo especificado no transporte.

        Este método lida com diferentes tipos de dados, incluindo primitivos (str, int, float),
        UUIDs, datas, arquivos e coleções como listas e dicionários. Também suporta campos aninhados
        definidos por outros `Transport`.

        Args:
            value (Any): Valor do campo a ser serializado.
            field_type (Any): Tipo esperado do campo conforme definido no transporte.

        Returns:
            Any: Valor serializado.

        Raises:
            TypeError: Se o tipo do campo não for suportado.
        """

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
