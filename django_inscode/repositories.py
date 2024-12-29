from django.db import transaction
from django.db.models import Model, QuerySet
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError, ObjectDoesNotExist

from uuid import UUID
from typing import TypeVar, List, Dict, Any

from .exceptions import BadRequest, InternalServerError, NotFound

T = TypeVar("T", bound=Model)


class Repository:
    def __init__(self, model: T):
        self.model = model

    def _format_validation_errors(self, error: ValidationError) -> List[Dict[str, Any]]:
        """
        Formata os erros de validação do Django no formato esperado.
        """
        errors = []
        if hasattr(error, "error_dict"):
            for field, field_errors in error.error_dict.items():
                for field_error in field_errors:
                    errors.append({"field": field, "message": field_error.message})
        elif hasattr(error, "error_list"):
            for field_error in error.error_list:
                errors.append({"field": None, "message": field_error.message})
        return errors

    def _save(
        self, instance: T, many_to_many_data: Dict[str, List[Any]] = None
    ) -> None:
        """
        Salva a instância no banco de dados, incluindo campos ManyToMany.
        """
        with transaction.atomic():
            try:
                instance.full_clean()
                instance.save()

                if many_to_many_data:
                    for field_name, value in many_to_many_data.items():
                        field_object = instance._meta.get_field(field_name)

                        if not isinstance(value, list):
                            raise BadRequest(
                                message=f"Invalid data for ManyToMany field '{field_name}'. Expected a list.",
                                errors=[
                                    {
                                        "field": field_name,
                                        "message": "Expected a list of IDs or instances.",
                                    }
                                ],
                            )

                        if all(isinstance(v, (int, UUID)) for v in value):
                            related_objects = field_object.related_model.objects.filter(
                                pk__in=value
                            )
                            if len(related_objects) != len(value):
                                raise BadRequest(
                                    message=f"Some related objects for '{field_name}' were not found.",
                                    errors=[
                                        {
                                            "field": field_name,
                                            "message": "Invalid IDs in the list.",
                                        }
                                    ],
                                )
                            getattr(instance, field_name).set(related_objects)
                        else:
                            getattr(instance, field_name).set(value)

            except ValidationError as e:
                raise BadRequest(errors=self._format_validation_errors(e))
            except Exception as e:
                raise InternalServerError(errors=[{"field": None, "message": str(e)}])

    def create(self, **data) -> T:
        """
        Cria uma nova instância no banco de dados.
        """
        many_to_many_data = {}

        for field_name, value in data.items():
            field_object = self.model._meta.get_field(field_name)
            if field_object.many_to_many:
                many_to_many_data[field_name] = value

        for field_name in many_to_many_data.keys():
            data.pop(field_name)

        instance = self.model(**data)
        self._save(instance, many_to_many_data)
        return instance

    def read(self, id: UUID | int) -> T:
        """
        Busca uma instância existente no banco de dados via id.
        """
        try:
            instance = self.model.objects.get(id=id)
            return instance
        except self.model.DoesNotExist:
            raise NotFound(message=f"{self.model._meta.object_name} não encontrado")

    def update(self, id: UUID | int, **data) -> T:
        """
        Atualiza a instância de um modelo com base nos dados fornecidos.
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

            if field_name in editable_fields:
                field_object = instance._meta.get_field(field_name)

                if field_object.is_relation and field_object.many_to_one:
                    if value is not None:
                        if isinstance(value, field_object.related_model):
                            setattr(instance, field_name, value)
                        else:
                            try:
                                related_object = field_object.related_model.objects.get(
                                    pk=value
                                )
                                setattr(instance, field_name, related_object)
                            except ObjectDoesNotExist:
                                raise BadRequest(
                                    message=f"Related object with ID '{value}' not found.",
                                    errors=[
                                        {
                                            "field": field_name,
                                            "message": "Invalid foreign key reference.",
                                        }
                                    ],
                                )
                    else:
                        setattr(instance, field_name, None)

                elif field_object.is_relation and field_object.many_to_many:
                    many_to_many_data[field_name] = value

                else:
                    setattr(instance, field_name, value)

        self._save(instance, many_to_many_data)
        return instance

    def delete(self, id: UUID | int) -> None:
        instance = self.read(id)

        with transaction.atomic():
            try:
                instance.delete()
            except Exception as e:
                raise InternalServerError(errors=[{"field": None, "message": str(e)}])

    def list_all(self) -> QuerySet[T]:
        """
        Retorna todas as instâncias de um modelo.
        """
        return self.model.objects.all()

    def filter(self, **kwargs) -> QuerySet[T]:
        """
        Retorna todas as instâncias do modelo que atendem ao filtro.
        """
        return self.model.objects.filter(**kwargs)