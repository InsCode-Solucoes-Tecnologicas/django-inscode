from django.views import View
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, JsonResponse

from typing import Set, Dict, Any, Optional, List, TypeVar, Type, Union

from . import mixins
from . import exceptions
from . import settings

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

    Esta classe fornece métodos e atributos genéricos para gerenciar permissões,
    serviços e validações, servindo como base para outras views.

    Attributes:
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    service: t_service = None
    permissions_classes: List[Type[t_permission]] = None
    fields: List[str] = []

    def __init__(self, **kwargs) -> None:
        """
        Inicializa a view e valida os atributos obrigatórios.

        Args:
            **kwargs: Argumentos adicionais para inicialização.
        """
        super().__init__(**kwargs)
        self._validate_required_attributes()

    def _validate_required_attributes(self) -> None:
        """
        Valida se os atributos obrigatórios foram definidos.

        Raises:
            ImproperlyConfigured: Se algum atributo obrigatório estiver ausente.
        """
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
        """
        Retorna o serviço associado à view.

        Returns:
            t_service: Serviço associado.
        """
        return self.service

    def get_context(self, request) -> Dict[str, Any]:
        """
        Retorna o contexto adicional para operações no serviço.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.

        Returns:
            Dict[str, Any]: Contexto adicional com informações do usuário e sessão.
        """
        return {"user": request.user, "session": request.session}

    def get_permissions(self) -> List[BasePermission]:
        """
        Instancia e retorna as classes de permissão configuradas.

        Returns:
            List[BasePermission]: Lista de instâncias das classes de permissão.
        """
        if not self.permissions_classes:
            return []
        return [permission() for permission in self.permissions_classes]

    def get_object(self):
        """Método para retornar o objeto atrelado à View"""
        pass

    def check_permissions(self, request: HttpRequest, obj: Any = None) -> None:
        """
        Verifica se todas as permissões são concedidas.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            obj (Any, optional): Objeto específico para verificar permissões de objeto.

        Raises:
            exceptions.Forbidden: Se alguma permissão for negada.
        """
        for permission in self.get_permissions():
            if not permission.has_permission(request, self):
                raise exceptions.Forbidden(message=permission.message)

            if obj and not permission.has_object_permission(request, self, obj):
                raise exceptions.Forbidden(message=permission.message)

    def verify_fields(self, data: Dict) -> None:
        """Verifica se todos os campos obrigatórios estão presentes nos dados."""
        missing_fields = set(self.get_fields()) - set(data.keys())

        if missing_fields:
            raise exceptions.BadRequest(
                f"Campos obrigatórios faltando: {', '.join(missing_fields)}"
            )

    def dispatch(self, request, *args, **kwargs):
        """
        Sobrescreve o método dispatch para verificar permissões antes de processar a requisição.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos posicionais adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            HttpResponse: Resposta processada pela view.

        Raises:
            exceptions.Forbidden: Se as permissões forem negadas.
        """
        self.check_permissions(request)

        if hasattr(self, "get_object") and callable(self.get_object):
            try:
                obj = self.get_object()
                self.check_permissions(request, obj)
            except exceptions.BadRequest:
                pass

        return super().dispatch(request, *args, **kwargs)


class GenericOrchestratorView(GenericView, mixins.ContentTypeHandlerMixin):
    """
    Classe base para views que lidam com lógica orquestrada.

    Utiliza serviços orquestradores para executar operações complexas que envolvem múltiplos
    repositórios ou lógicas de negócio avançadas.

    Attributes:
        service (t_orchestrator_service): Serviço orquestrador associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    service: t_orchestrator_service = None

    def execute(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Método principal para executar a lógica orquestrada delegada ao serviço orquestrador.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos posicionais adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo o resultado da operação.

        Raises:
            exceptions.BadRequest: Se os dados enviados forem inválidos.
            exceptions.Forbidden: Se as permissões forem negadas.
        """
        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        self.verify_fields(data)
        context = self.get_context(request)
        service = self.get_service()

        result = service.execute(*args, data=data, context=context, **kwargs)

        if self.serializer:
            result = self.get_serializer().serialize(result)

        return JsonResponse(result, status=200)


class GenericModelView(GenericView):
    """
    Classe base genérica que combina mixins para criar views RESTful.

    Esta classe fornece funcionalidades para manipular modelos Django de forma padronizada,
    incluindo suporte para serialização, paginação e operações CRUD (Create, Read, Update, Delete).
    É projetada para ser estendida por outras views que necessitam de lógica específica.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        paginate_by (int): Número de itens por página para paginação. Default é definido em `settings.DEFAULT_PAGINATED_BY`.
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    serializer: t_serializer = None
    lookup_field: str = "pk"
    paginate_by: int = settings.DEFAULT_PAGINATED_BY

    def _validate_required_attributes(self):
        """
        Valida se os atributos obrigatórios foram definidos.

        Atributos obrigatórios incluem `service` e `serializer`.

        Raises:
            ImproperlyConfigured: Se algum atributo obrigatório estiver ausente.
        """
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
        """
        Retorna os campos obrigatórios para requisições de criação.

        Returns:
            Set[str]: Conjunto de nomes dos campos permitidos.
        """
        return self.fields

    def get_lookup_value(self):
        """
        Retorna o valor do campo de lookup usado para identificar uma instância específica.

        Returns:
            Any: Valor do campo de lookup obtido dos argumentos da URL.
        """
        return self.kwargs.get(self.lookup_field)

    def get_object(self):
        """
        Recupera uma instância específica do modelo com base no campo de lookup.

        Returns:
            Model: Instância do modelo correspondente ao valor de lookup.

        Raises:
            exceptions.BadRequest: Se nenhum identificador for especificado.
            exceptions.NotFound: Se o objeto não for encontrado.
        """
        lookup_value = self.get_lookup_value()

        if not lookup_value:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        context = self.get_context(self.request)

        return self.service.perform_action("read", lookup_value, context=context)

    def get_serializer(self):
        """
        Retorna a classe de serializador associada à view.

        Returns:
            Serializer: Instância da classe de serializador configurada.

        Raises:
            ImproperlyConfigured: Se o atributo `serializer` não estiver definido.
        """
        return self.serializer

    def serialize_object(self, obj):
        """
        Serializa uma instância do modelo usando o serializador configurado.

        Args:
            obj (Model): Instância do modelo a ser serializada.

        Returns:
            Dict[str, Any]: Dicionário contendo os dados serializados da instância.

        Raises:
            ValueError: Se ocorrer um erro durante a serialização.
        """
        serializer = self.get_serializer()
        return serializer.serialize(obj)


class CreateModelView(GenericModelView, mixins.ViewCreateModelMixin):
    """
    View para criar uma nova instância.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """


class RetrieveModelView(GenericModelView, mixins.ViewRetrieveModelMixin):
    """
    View para recuperar e listar instâncias.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        paginate_by (int): Número de itens por página para paginação. Default é definido em `settings.DEFAULT_PAGINATED_BY`.
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
    """


class UpdateModelView(GenericModelView, mixins.ViewUpdateModelMixin):
    """
    View para atualizar parcialmente uma instância.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """


class DeleteModelView(GenericModelView, mixins.ViewDeleteModelMixin):
    """
    View para excluir uma instância.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
    """


class ModelView(
    GenericModelView,
    mixins.ViewCreateModelMixin,
    mixins.ViewRetrieveModelMixin,
    mixins.ViewUpdateModelMixin,
    mixins.ViewDeleteModelMixin,
):
    """
    View que combina todas as operações CRUD em um único endpoint.

    Esta classe fornece suporte completo para criar, ler (listar e recuperar),
    atualizar e excluir instâncias de um modelo Django. É ideal para casos simples
    onde a lógica CRUD básica é suficiente.

    Métodos herdados incluem validação de campos, paginação e serialização automática.

    Attributes:
        serializer (t_serializer): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        paginate_by (int): Número de itens por página para paginação. Default é definido em `settings.DEFAULT_PAGINATED_BY`.
        service (t_service): Serviço associado à view.
        permissions_classes (List[Type[t_permission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    pass
