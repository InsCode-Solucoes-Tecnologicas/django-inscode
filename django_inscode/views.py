from django.views import View
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse

from typing import Set, Dict, Any, Optional

import mixins
import exceptions
import json


class GenericView(View):
    """
    Classe base genérica para views que compartilham lógica comum.
    """

    service = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate_required_attributes()

    def _validate_required_attributes(self):
        """Valida se os atributos obrigatórios foram definidos."""
        required_attributes = {"service"}
        missing_attributes = [
            attr for attr in required_attributes if not getattr(self, attr)
        ]

        if missing_attributes:
            raise ImproperlyConfigured(
                f"A classe {self.__class__.__name__} deve definir os atributos: "
                f"{', '.join(missing_attributes)}"
            )

    def get_service(self):
        """Retorna o serviço associado."""
        return self.service

    def get_context(self, request) -> Dict[str, Any]:
        """Retorna o contexto adicional para operações no serviço."""
        return {"user": request.user, "session": request.session}


class GenericOrchestratorView(GenericView):
    """
    Classe base para views que lidam com lógica orquestrada.
    Utiliza serviços orquestradores para executar operações complexas.
    """

    def execute(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Método principal para executar a lógica orquestrada.
        Delegado ao serviço orquestrador.
        """
        data = json.loads(request.body) if request.body else {}

        context = self.get_context(request)
        service = self.get_service()

        result = service.execute(data=data, context=context, *args, **kwargs)

        if self.serializer:
            result = self.get_serializer().serialize(result)

        return JsonResponse(result, status=200)


class GenericModelView(GenericView):
    """
    Classe base genérica que combina mixins para criar views RESTful.
    """

    serializer = None
    lookup_field: str = "pk"
    fields: Set[str] = set()
    paginate_by: int = 10

    def _validate_required_attributes(self):
        """Valida se os atributos obrigatórios foram definidos."""
        required_attributes = {"service", "serializer"}
        missing_attributes = [
            attr for attr in required_attributes if not getattr(self, attr)
        ]

        if missing_attributes:
            raise ImproperlyConfigured(
                f"A classe {self.__class__.__name__} deve definir os atributos: "
                f"{', '.join(missing_attributes)}"
            )

    def get_fields(self) -> Set[str]:
        """Retorna os campos permitidos para serialização."""
        return self.fields

    def verify_fields(self, data: Dict) -> None:
        """Verifica se todos os campos obrigatórios estão presentes nos dados."""
        missing_fields = self.get_fields() - set(data.keys())

        if missing_fields:
            raise exceptions.BadRequest(
                f"Campos obrigatórios faltando: {', '.join(missing_fields)}"
            )

    def get_object(self):
        """Recupera uma instância específica."""
        lookup_value = self.kwargs.get(self.lookup_field)

        if not lookup_value:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        context = self.get_context(self.request)

        return self.service.perform_action("read", lookup_value, context=context)

    def get_queryset(self, filter_kwargs: Optional[Dict[str, Any]] = None):
        """Retorna o queryset filtrado."""
        filter_kwargs = filter_kwargs or {}

        context = self.get_context(self.request)

        return self.service.perform_action(
            "filter", filter_kwargs=filter_kwargs, context=context
        )

    def paginate_queryset(self, queryset, page_number):
        """Paginação básica do queryset."""

        start = (page_number - 1) * self.paginate_by
        end = start + self.paginate_by

        return queryset[start:end]

    def get_serializer(self):
        return self.serializer

    def serialize_object(self, obj):
        serializer = self.get_serializer()
        return serializer.serialize(obj)


class CreateModelView(GenericModelView, mixins.CreateModelMixin):
    """View para criar uma nova instância."""


class RetrieveModelView(GenericModelView, mixins.RetrieveModelMixin):
    """View para recuperar uma única instância."""


class ListModelView(GenericModelView, mixins.ListModelMixin):
    """View para listar instâncias."""


class UpdateModelView(GenericModelView, mixins.UpdateModelMixin):
    """View para atualizar parcialmente uma instância."""


class DeleteModelView(GenericModelView, mixins.DeleteModelMixin):
    """View para excluir uma instância."""


class ModelView(
    GenericModelView,
    mixins.ViewCreateModelMixin,
    mixins.ViewRetrieveModelMixin,
    mixins.ViewUpdateModelMixin,
    mixins.ViewDeleteModelMixin,
    mixins.ViewListModelMixin,
):
    """View para lidar com todos os métodos para um modelo."""

    pass
