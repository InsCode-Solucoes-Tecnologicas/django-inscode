from django.views import View
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse

from typing import Set, Dict, Any, Optional, List, TypeVar, Type, Union

import mixins
import exceptions
import settings

from .permissions import BasePermission
from .services import GenericModelService, OrchestratorService
from .serializers import Serializer

t_permission = TypeVar("t_permission", bound=BasePermission)
t_generic_model_service = TypeVar("t_generic_model_service", bound=GenericModelService)
t_orchestrator_service = TypeVar("t_orchestrator_service", bound=OrchestratorService)
t_serializer = TypeVar("t_serializer", bound=Serializer)
t_service = Union[t_generic_model_service, t_orchestrator_service]


class GenericView(View):
    """
    Classe base genérica para views que compartilham lógica comum.
    """

    service: t_service = None
    permissions_classes: List[Type[t_permission]] = None

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._validate_required_attributes()

    def _validate_required_attributes(self) -> None:
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

    def get_service(self) -> t_service:
        """Retorna o serviço associado."""
        return self.service

    def get_context(self, request) -> Dict[str, Any]:
        """Retorna o contexto adicional para operações no serviço."""
        return {"user": request.user, "session": request.session}

    def get_permissions(self) -> List[BasePermission]:
        """
        Instancia e retorna as classes de permissão configuradas.
        """
        if not self.permissions_classes:
            return []
        return [permission() for permission in self.permissions_classes]

    def get_obj(self):
        """Método para retornar o objeto atrelado à View"""
        pass

    def check_permissions(self, request: HttpRequest, obj: Any = None) -> None:
        """
        Verifica se todas as permissões são concedidas.

        Sempre verifica `has_permission`.
        Se um objeto for fornecido, também verifica `has_object_permission`.
        """
        for permission in self.get_permissions():
            if not permission.has_permission(request, self):
                raise exceptions.Forbidden(message=permission.message)

            if obj and not permission.has_object_permission(request, self, obj):
                raise exceptions.Forbidden(message=permission.message)

    def dispatch(self, request, *args, **kwargs):
        """
        Sobrescreve o método dispatch para verificar permissões.
        """
        self.check_permissions(request)

        if hasattr(self, "get_obj") and callable(self.get_obj):
            try:
                obj = self.get_obj()
                self.check_permissions(request, obj)
            except exceptions.BadRequest:
                pass

        return super().dispatch(request, *args, **kwargs)


class GenericOrchestratorView(GenericView, mixins.ContentTypeHandlerMixin):
    """
    Classe base para views que lidam com lógica orquestrada.
    Utiliza serviços orquestradores para executar operações complexas.
    """

    service: t_orchestrator_service = None

    def execute(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Método principal para executar a lógica orquestrada.
        Delegado ao serviço orquestrador.
        """
        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        context = self.get_context(request)
        service = self.get_service()

        result = service.execute(*args, data=data, context=context, **kwargs)

        if self.serializer:
            result = self.get_serializer().serialize(result)

        return JsonResponse(result, status=200)


class GenericModelView(GenericView):
    """
    Classe base genérica que combina mixins para criar views RESTful.
    """

    serializer: t_serializer = None
    lookup_field: str = "pk"
    fields: List[str] = []
    paginate_by: int = settings.DEFAULT_PAGINATED_BY

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

    def get_lookup_value(self):
        """Retorna o valor do campo de lookup"""
        return self.kwargs.get(self.lookup_field)

    def get_object(self):
        """Recupera uma instância específica."""
        lookup_value = self.get_lookup_value()

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


class CreateModelView(GenericModelView, mixins.ViewCreateModelMixin):
    """View para criar uma nova instância."""


class RetrieveModelView(GenericModelView, mixins.ViewRetrieveModelMixin):
    """View para recuperar e listar instâncias."""


class UpdateModelView(GenericModelView, mixins.ViewUpdateModelMixin):
    """View para atualizar parcialmente uma instância."""


class DeleteModelView(GenericModelView, mixins.ViewDeleteModelMixin):
    """View para excluir uma instância."""


class ModelView(
    GenericModelView,
    mixins.ViewCreateModelMixin,
    mixins.ViewRetrieveModelMixin,
    mixins.ViewUpdateModelMixin,
    mixins.ViewDeleteModelMixin,
):
    """View para lidar com todos os métodos para um modelo."""

    pass
