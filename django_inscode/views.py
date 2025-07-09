from django.views import View
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, JsonResponse

from typing import Set, Dict, Any, List, Union, ClassVar

from . import mixins
from . import exceptions

from .permissions import BasePermission
from .services import GenericModelService, OrchestratorService
from .serializers import SerializerInterface, SerializerFactory
from .authentication import BaseAuthentication

import json

Service = Union[GenericModelService, OrchestratorService]
Context = Dict[str, Any]
Data = Dict[str, Any]


class GenericView(View):
    """
    Classe base genérica para views que compartilham lógica comum.

    Esta classe fornece métodos e atributos genéricos para gerenciar permissões,
    serviços e validações, servindo como base para outras views.

    Attributes:
        service (Service): Serviço associado à view.
        permissions_classes (List[Type[BasePermission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    service: ClassVar[Service] = None
    permissions_classes: ClassVar[List[BasePermission]] = None
    fields: ClassVar[List[str]] = []
    authentication_classes: ClassVar[List[BaseAuthentication]] = []

    def __init__(self, **kwargs) -> None:
        """
        Inicializa a view e valida os atributos obrigatórios.

        Args:
            **kwargs: Argumentos adicionais para inicialização.
        """
        super().__init__(**kwargs)
        self._validate_required_attributes()

    def perform_authentication(self, request) -> None:
        """
        Executa a autenticação iterando sobre as classes configuradas.
        Popula request.user com o usuário autenticado ou AnonymousUser.
        """
        request.user = AnonymousUser()

        for authenticator_class in self.authentication_classes:
            authenticator = authenticator_class()
            try:
                user = authenticator.authenticate(request)
                if user is not None:
                    request.user = user
                    return
            except exceptions.Unauthorized as e:
                raise exceptions.Unauthorized(str(e))

    def _parse_request_data(self, request: HttpRequest) -> Dict[str, Any]:
        """
        Analisa os dados da requisição com base no tipo de conteúdo.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.

        Returns:
            Dict[str, Any]: Dados analisados da requisição.

        Raises:
            ValueError: Se o formato do conteúdo não for suportado ou se o JSON for inválido.
        """
        if request.content_type == "application/json":
            try:
                return json.loads(request.body) if request.body else {}
            except json.JSONDecodeError:
                raise ValueError("JSON inválido na requisição.")
        elif request.content_type.startswith("multipart/form-data"):
            data = request.POST.dict()
            files = {key: request.FILES[key] for key in request.FILES}
            return {**data, **files}
        else:
            return {}

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

    def get_service(self) -> Service:
        """
        Retorna o serviço associado à view.

        Returns:
            Service: Serviço associado.
        """
        return self.service

    def get_context(self, request) -> Context:
        """
        Retorna o contexto adicional para operações no serviço.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.

        Returns:
            Context: Contexto adicional com informações do usuário, sessão e view.
        """
        return {
            "user": request.user,
            "session": request.session,
            "url_params": self.kwargs,
            "query_params": request.GET.dict(),
        }

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

    def get_fields(self) -> Set[str]:
        """
        Retorna os campos obrigatórios para requisições de criação.

        Returns:
            Set[str]: Conjunto de nomes dos campos permitidos.
        """
        return self.fields or []

    def verify_fields(self, data: Data) -> None:
        """Verifica se todos os campos obrigatórios estão presentes nos dados."""
        missing_fields = set(self.get_fields()) - set(data.keys())

        if missing_fields:
            raise exceptions.BadRequest(
                f"Campos obrigatórios faltando: {[', '.join(missing_fields)]}"
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
        if self.authentication_classes:
            self.perform_authentication(request)

        if not hasattr(request, "data"):
            try:
                request.data = self._parse_request_data(request)
            except Exception as e:
                raise exceptions.BadRequest(
                    message="Formato de requisição inválido", errors=str(e)
                )

        self.check_permissions(request)

        if hasattr(self, "get_object") and callable(self.get_object):
            try:
                obj = self.get_object()
                self.check_permissions(request, obj)
            except exceptions.BadRequest:
                pass

        return super().dispatch(request, *args, **kwargs)


class GenericOrchestratorView(GenericView):
    """
    Classe base para views que lidam com lógica orquestrada.

    Utiliza serviços orquestradores para executar operações complexas que envolvem múltiplos
    repositórios ou lógicas de negócio avançadas.

    Attributes:
        service (OrchestratorService): Serviço orquestrador associado à view.
        permissions_classes (List[Type[BasePermission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    service: ClassVar[OrchestratorService] = None

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
        data = request.data
        self.verify_fields(data)
        context = self.get_context(request)
        service = self.get_service()

        result = service.execute(
            *args, data=data, request=request, context=context, **kwargs
        )

        return JsonResponse(result, status=200)


class GenericModelView(GenericView):
    """
    Classe base genérica que combina mixins para criar views RESTful.

    Esta classe fornece funcionalidades para manipular modelos Django de forma padronizada,
    incluindo suporte para serialização, paginação e operações CRUD (Create, Read, Update, Delete).
    É projetada para ser estendida por outras views que necessitam de lógica específica.

    Attributes:
        serializer (SerializerInterface): Classe de serializador associada à view.
        service (GenericModelService): Serviço associado à view.
        permissions_classes (List[Type[BasePermission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    serializer: ClassVar[SerializerInterface] = None
    service: ClassVar[GenericModelService] = None
    lookup_field: ClassVar[str] = "pk"

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
        return SerializerFactory.get_serializer(self.serializer)

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
        serializer (SerializeInterface): Classe de serializador associada à view.
        lookup_field (str): Nome do campo usado para identificar instâncias específicas. Default é "pk".
        paginate_by (int): Número de itens por página para paginação. Default é definido em `settings.DEFAULT_PAGINATED_BY`.
        service (GenericModelService): Serviço associado à view.
        permissions_classes (List[Type[BasePermission]]): Lista de classes de permissão.
        fields (List[str]): Lista de campos permitidos na view.
    """

    pass


__all__ = [
    "GenericView",
    "GenericOrchestratorView",
    "GenericModelView",
    "CreateModelView",
    "RetrieveModelView",
    "UpdateModelView",
    "DeleteModelView",
    "ModelView",
]
