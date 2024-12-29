from django.http import JsonResponse, HttpRequest
from django.views import View
from django.core.exceptions import ImproperlyConfigured
from typing import Set, Dict, Any, Optional, TypeVar

import json
import mixins

t_model = TypeVar("t_model")


class GenericView(View):
    """
    Classe base genérica que combina mixins para criar views RESTful.
    """

    service = None
    serializer = None
    lookup_field: str = "pk"
    fields: Set[str] = set()
    paginate_by: int = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate_required_attributes()

    def _validate_required_attributes(self) -> None:
        required_attributes = {"service", "serializer"}
        missing_attributes = [
            attr for attr in required_attributes if not getattr(self, attr)
        ]

        if missing_attributes:
            raise ImproperlyConfigured(
                f"A classe {self.__class__.__name__} deve definir os atributos: {', '.join(missing_attributes)}"
            )

    def get_fields(self) -> Set[str]:
        """Retorna os campos permitidos para serialização."""
        return self.fields

    def verify_fields(self, data: Dict) -> None:
        """Verifica se todos os campos obrigatórios estão presentes nos dados."""
        missing_fields = self.get_fields() - set(data.keys())

        if missing_fields:
            raise BadRequest(
                f"Campos obrigatórios faltando: {', '.join(missing_fields)}"
            )

    def serialize_object(self, obj: t_model) -> Dict[str, Any]:
        """Serializa um objeto do modelo."""
        return self.serializer(obj)

    def get_object(self):
        """Recupera uma instância específica."""
        lookup_value = self.kwargs.get(self.lookup_field)

        if not lookup_value:
            raise PermissionDenied("Nenhum identificador especificado.")

        return self.service.read_by_id(lookup_value)

    def get_queryset(self, filter_kwargs: Optional[Dict[str, Any]] = None):
        """Retorna o queryset filtrado."""
        filter_kwargs = filter_kwargs or {}

        return self.service.filter(**filter_kwargs)

    def paginate_queryset(self, queryset, page_number):
        """Paginação básica do queryset."""

        start = (page_number - 1) * self.paginate_by
        end = start + self.paginate_by

        return queryset[start:end]

    def get_context(self, request):
        """Retorna o contexto adicional para operações no serviço."""

        return {"user": request.user}


class CreateModelView(GenericView, CreateModelMixin):
    """View para criar uma nova instância."""


class RetrieveModelView(GenericView, RetrieveModelMixin):
    """View para recuperar uma única instância."""


class ListModelView(GenericView, ListModelMixin):
    """View para listar instâncias."""


class UpdateModelView(GenericView, UpdateModelMixin):
    """View para atualizar parcialmente uma instância."""


class DeleteModelView(GenericView, DeleteModelMixin):
    """View para excluir uma instância."""

class ModelView(GenericView)