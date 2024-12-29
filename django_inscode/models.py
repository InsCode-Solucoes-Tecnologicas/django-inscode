from django_softdelete.models import SoftDeleteModel
from django.db import models

from uuid import uuid4


class BaseModel(models.Model):
    """
    Modelo base contendo um id no formato uuid4 como chave primária.
    """

    id = models.UUIDField(primary_key=True, blank=True, default=uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteBaseModel(SoftDeleteModel):
    """
    Modelo base contendo um id no formato uuid4 como chave primária. Além disso este
    modelo não pode ser excluído do banco de dados permanentemente.
    """

    id = models.UUIDField(primary_key=True, blank=True, default=uuid4, editable=False)

    class Meta:
        abstract = True
