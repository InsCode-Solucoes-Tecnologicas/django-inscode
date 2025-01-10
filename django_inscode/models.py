from django_softdelete.models import SoftDeleteModel
from django.db import models

from uuid import uuid4


class BaseModel(models.Model):
    """
    Modelo base abstrato que fornece um campo `id` como chave primária no formato UUID.

    Este modelo é utilizado como base para outros modelos, garantindo que cada instância
    tenha um identificador único gerado automaticamente.

    Attributes:
        id (UUIDField): Campo de chave primária gerado automaticamente no formato UUID.
    """

    id = models.UUIDField(primary_key=True, blank=True, default=uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteBaseModel(SoftDeleteModel):
    """
    Modelo base abstrato que fornece um campo `id` como chave primária no formato UUID e suporte a exclusão lógica.

    Este modelo é utilizado como base para outros modelos que requerem exclusão lógica,
    ou seja, os registros não são removidos permanentemente do banco de dados.

    Attributes:
        id (UUIDField): Campo de chave primária gerado automaticamente no formato UUID.

    Inherits:
        SoftDeleteModel: Implementa a funcionalidade de exclusão lógica.
    """

    id = models.UUIDField(primary_key=True, blank=True, default=uuid4, editable=False)

    class Meta:
        abstract = True
