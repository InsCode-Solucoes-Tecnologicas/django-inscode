from django.db import transaction
from django.db.models import Model, QuerySet
from django.utils.translation import gettext as _
from django.core.exceptions import (
    ValidationError,
    ObjectDoesNotExist,
    FieldDoesNotExist,
)
from django.db.models.fields.related import ManyToManyRel, ManyToManyField

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
                                ids = [
                                    UUID(str(v)) if isinstance(v, str) else v
                                    for v in value
                                ]

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

        editable_fields = [
            field.name
            for field in instance._meta.get_fields()
            if getattr(field, "editable", True)
        ]

        many_to_many_data = {}

        for key, value in data.items():
            field_name = key[:-3] if key.endswith("_id") else key

            try:
                field = instance._meta.get_field(field_name)

                if isinstance(field, (ManyToManyRel, ManyToManyField)):
                    many_to_many_data[field_name] = value

            except FieldDoesNotExist:
                raise BadRequest(
                    message=f"Campo inexistente.",
                    errors={f"{field_name}": "Este campo não existe no modelo."},
                )

            if field_name in editable_fields:
                try:
                    field_object = instance._meta.get_field(field_name)

                    if isinstance(field_object, (ManyToManyField, ManyToManyRel)):
                        continue

                    if field_object.is_relation and field_object.many_to_one:
                        if value is None:
                            setattr(instance, field_name, None)
                        else:
                            if isinstance(value, field_object.related_model):
                                related_instance = value
                            else:
                                related_instance = (
                                    field_object.related_model.objects.get(pk=value)
                                )

                            setattr(instance, field_name, related_instance)

                    else:
                        setattr(instance, field_name, value)

                except ObjectDoesNotExist:
                    raise BadRequest(
                        message=f"Objeto relacionado não encontrado para o campo '{field_name}'",
                        errors={f"{field_name}": "Referência inválida"},
                    )
                except FieldDoesNotExist:
                    raise BadRequest(
                        message=f"Campo inválido: '{field_name}'",
                        errors={
                            f"{field_name}": "Campo não existe",
                        },
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


__all__ = ["Repository"]
