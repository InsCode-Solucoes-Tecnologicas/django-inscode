from django.db import transaction
from django.db.models import Model, QuerySet, Manager, Q
from django.utils.translation import gettext as _
from django.core.exceptions import (
    ValidationError,
    ObjectDoesNotExist,
    FieldDoesNotExist,
)
from django.db.models.fields.related import ManyToManyRel, ManyToManyField
from django.apps import apps

from django_softdelete.models import SoftDeleteModel

from uuid import UUID
from typing import TypeVar, List, Dict, Any

from .exceptions import BadRequest, InternalServerError, NotFound

T = TypeVar("T", bound=Model)


class Repository:
    """
    Repositório genérico para manipulação de modelos Django.

    Esta classe fornece métodos para realizar operações CRUD (Create, Read, Update, Delete)
    e outras interações com o banco de dados de forma genérica.

    Attributes:
        model (Model): O modelo Django associado ao repositório.
    """

    def __init__(self, model: T):
        """
        Inicializa o repositório com o modelo Django associado.

        Args:
            model (Model): O modelo Django que será manipulado pelo repositório.
        """
        self.model = model

    def _format_validation_errors(self, error: ValidationError) -> List[Dict[str, Any]]:
        """
        Formata os erros de validação do Django no formato esperado.

        Args:
            error (ValidationError): Exceção de validação capturada.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários contendo os campos e mensagens de erro.
        """
        errors = []
        if hasattr(error, "error_dict"):
            for field, field_errors in error.error_dict.items():
                for field_error in field_errors:
                    message = (
                        field_error.message % field_error.params
                        if field_error.params
                        else field_error.message
                    )
                    errors.append({"field": field, "message": message})
        elif hasattr(error, "error_list"):
            for field_error in error.error_list:
                message = (
                    field_error.message % field_error.params
                    if field_error.params
                    else field_error.message
                )
                errors.append({"field": None, "message": message})
        return errors

    def _save(
        self, instance: T, many_to_many_data: Dict[str, List[Any]] = None
    ) -> None:
        """
        Salva a instância no banco de dados, incluindo campos ManyToMany.

        Args:
            instance (Model): Instância do modelo a ser salva.
            many_to_many_data (Dict[str, List[Any]], optional): Dados para campos ManyToMany.

        Raises:
            BadRequest: Se houver problemas nos dados fornecidos.
            InternalServerError: Se ocorrer um erro inesperado durante o salvamento.
        """
        with transaction.atomic():
            try:
                instance.full_clean()
                instance.save()

                if many_to_many_data:
                    for field_name, value in many_to_many_data.items():
                        try:
                            field = instance._meta.get_field(field_name)

                            if isinstance(field, (ManyToManyField, ManyToManyRel)):
                                related_model = field.remote_field.model

                        except FieldDoesNotExist:
                            raise BadRequest(
                                message=f"Campo inexistente.",
                                errors={
                                    f"{field_name}": "Este campo não existe no modelo."
                                },
                            )

                        if not isinstance(value, (list, QuerySet)):
                            raise BadRequest(
                                message=f"Valor inválido para o campo ManyToMany.",
                                errors={
                                    f"{field_name}": "Esperada uma lista de IDs ou instâncias."
                                },
                            )

                        if all(isinstance(v, (int, UUID, str)) for v in value):
                            try:
                                ids = [str(v) for v in value]

                                related_objects = related_model.objects.filter(
                                    pk__in=ids
                                )

                                if len(related_objects) != len(value):
                                    ids_found = set(
                                        related_objects.values_list("pk", flat=True)
                                    )

                                    missing_ids = set(ids) - ids_found

                                    raise BadRequest(
                                        message=f"Alguns objetos relacionados não foram encontrados.",
                                        errors={
                                            f"{field_name}": f"IDs inválidos: {missing_ids}."
                                        },
                                    )

                            except (ValueError, AttributeError):
                                raise BadRequest(
                                    message=f"IDs inválidos.",
                                    errors={
                                        f"{field_name}": "IDs malformados.",
                                    },
                                )
                        else:
                            related_objects = value

                        getattr(instance, field_name).set(related_objects)

            except ValidationError as e:
                raise BadRequest(errors=self._format_validation_errors(e))
            except Exception as e:
                raise InternalServerError(errors={"internal_server_error": str(e)})

    def create(self, **data) -> T:
        """
        Cria uma nova instância no banco de dados.
        Args:
            **data: Dados para criar a instância.
        Returns:
            Model: Instância criada do modelo.
        Raises:
            BadRequest: Se houver problemas nos dados fornecidos.
            InternalServerError: Se ocorrer um erro inesperado durante a criação.
        """
        if issubclass(self.model, SoftDeleteModel):
            self._handle_softdelete_uniqueness(data)

        many_to_many_data = {}

        for field_name, value in data.items():
            try:
                field = self.model._meta.get_field(field_name)
                if isinstance(field, (ManyToManyRel, ManyToManyField)):
                    many_to_many_data[field_name] = value
            except FieldDoesNotExist:
                raise BadRequest(
                    message=f"Campo inexistente.",
                    errors={f"{field_name}": "Este campo não existe no modelo."},
                )

        for key in many_to_many_data.keys():
            del data[key]

        instance = self.model(**data)

        self._save(instance, many_to_many_data)

        return instance

    def _handle_softdelete_uniqueness(self, data: dict):
        """
        Remove hard (definitivamente) objetos soft deleted que conflitam com campos únicos.
        """
        unique_fields = [
            field.name
            for field in self.model._meta.fields
            if getattr(field, "unique", False)
        ]
        unique_together = [
            tup for tup in getattr(self.model._meta, "unique_together", [])
        ]

        query = Q()
        for field in unique_fields:
            if field in data:
                query |= Q(**{field: data[field]})

        for fields in unique_together:
            if all(f in data for f in fields):
                filters = {f: data[f] for f in fields}
                query |= Q(**filters)

        if query:
            deleted_qs = self.model.deleted_objects.filter(query)
            for obj in deleted_qs:
                obj.hard_delete()

    def read(self, id: UUID | int) -> T:
        """
        Busca uma instância existente no banco de dados via ID.

        Args:
            id (UUID | int): Identificador da instância.

        Returns:
            Model: Instância encontrada do modelo.

        Raises:
            NotFound: Se a instância não for encontrada.
        """
        try:
            instance = self.model.objects.get(id=id)
            return instance
        except self.model.DoesNotExist:
            raise NotFound(message=f"{self.model._meta.object_name} não encontrado")

    def update(self, id: UUID | int, **data) -> T:
        """
        Atualiza uma instância existente e seus relacionamentos many-to-many (diretos e inversos).

        Args:
            id: UUID ou ID inteiro do objeto
            data: Dados para atualização, podendo incluir campos normais e relacionamentos

        Returns:
            Instância atualizada

        Raises:
            BadRequest: Em caso de dados inválidos
            NotFound: Se o objeto não existir
            InternalServerError: Para erros inesperados
        """
        instance = self.read(id)
        meta = instance._meta

        editable_fields = {
            field.name
            for field in meta.get_fields()
            if getattr(field, "editable", True)
        }
        many_to_many_data = {}

        for key, value in data.items():
            field_name = key[:-3] if key.endswith("_id") else key

            try:
                field = meta.get_field(field_name)
            except FieldDoesNotExist:
                raise BadRequest(
                    message=f"Campo '{field_name}' não existe no modelo.",
                    errors={field_name: "Este campo não existe no modelo."},
                )

            if isinstance(field, (ManyToManyField, ManyToManyRel)):
                many_to_many_data[field_name] = value
                continue

            if field_name not in editable_fields:
                continue

            try:
                if field.is_relation and (field.many_to_one or field.one_to_one):
                    if value is None:
                        setattr(instance, field_name, None)
                    else:
                        related_model = field.related_model
                        related_instance = (
                            value
                            if isinstance(value, related_model)
                            else related_model.objects.get(pk=value)
                        )
                        setattr(instance, field_name, related_instance)
                else:
                    setattr(instance, field_name, value)

            except ObjectDoesNotExist:
                raise BadRequest(
                    message=f"Objeto relacionado não encontrado para o campo '{field_name}'.",
                    errors={field_name: "Referência inválida"},
                )

        self._save(instance, many_to_many_data)

        return instance

    def delete(self, id: UUID | int) -> None:
        """
        Exclui uma instância existente no banco de dados via ID.

        Args:
            id (UUID | int): Identificador da instância a ser excluída.

        Raises:
            NotFound: Se a instância não for encontrada.
            InternalServerError: Se ocorrer um erro inesperado durante a exclusão.
        """
        instance = self.read(id)

        with transaction.atomic():
            try:
                instance.delete()
            except Exception as e:
                raise InternalServerError(errors=[{"field": None, "message": str(e)}])

    def list_all(self) -> QuerySet[T]:
        """
        Retorna todas as instâncias do modelo associadas ao repositório.

        Returns:
            QuerySet[T]: Conjunto de resultados contendo todas as instâncias do modelo.
        """
        return self.model.objects.all()

    def filter(self, **kwargs) -> QuerySet[T]:
        """
        Retorna todas as instâncias do modelo que atendem aos critérios de filtro fornecidos.

        Args:
            **kwargs: Argumentos de filtro para a consulta.

        Returns:
            QuerySet[T]: Conjunto de resultados contendo as instâncias que atendem aos filtros.
        """
        return self.model.objects.filter(**kwargs)

    @property
    def manager(self) -> Manager[Model]:
        """
        Retorna o manager para consultas mais complexas. Equivalente a acessar Model.objects

        Returns:
            BaseManager[Model]: Base manager do modelo.
        """
        return self.model.objects


__REPOSITORIES = {model._meta.label: Repository(model) for model in apps.get_models()}


def get_repository(model: str) -> Repository:
    if not isinstance(model, str):
        raise ValueError("model must be a string")

    if not model in __REPOSITORIES.keys():
        raise ValueError(f"model not registered in django apps: {model}")

    return __REPOSITORIES[model]


__all__ = ["Repository", "get_repository"]
