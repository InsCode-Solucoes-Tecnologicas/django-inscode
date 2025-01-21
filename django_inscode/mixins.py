from uuid import UUID
from typing import Dict, Any, TypeVar, Optional

from django.http import HttpRequest, JsonResponse
from django.db.models import QuerySet, Model

from . import exceptions

import json

t_model = TypeVar("t_model", bound=Model)


class ServiceCreateMixin:
    """
    Mixin para criar instâncias de um modelo em um serviço.

    Métodos:
        create: Cria uma nova instância do modelo.
    """

    def create(self, data: Dict, context: Dict) -> t_model:
        """
        Cria uma nova instância do modelo.

        Args:
            data (Dict): Dados para criação do objeto.
            context (Dict): Contexto adicional para a operação.

        Returns:
            t_model: Instância criada do modelo.
        """
        model_repository = self.get_model_repository()
        return model_repository.create(**data)


class ServiceReadMixin:
    """
    Mixin para ler instâncias de um modelo em um serviço.

    Métodos:
        read: Lê uma instância específica pelo ID.
        list: Lista instâncias filtradas do modelo.
    """

    def read(self, id: UUID | int, context: Dict) -> t_model:
        """
        Lê uma instância específica pelo ID.

        Args:
            id (UUID | int): Identificador da instância.
            context (Dict): Contexto adicional para a operação.

        Returns:
            t_model: Instância do modelo correspondente ao ID.
        """
        model_repository = self.get_model_repository()
        return model_repository.read(id)

    def list(self, context: Dict, **kwargs) -> QuerySet[t_model]:
        """
        Lista instâncias filtradas do modelo.

        Args:
            context (Dict): Contexto adicional para a operação.
            **kwargs: Filtros adicionais para a consulta.

        Returns:
            QuerySet[t_model]: Conjunto de resultados filtrados.
        """
        model_repository = self.get_model_repository()
        return model_repository.filter(**kwargs)


class ServiceUpdateMixin:
    """
    Mixin para atualizar instâncias de um modelo em um serviço.

    Métodos:
        update: Atualiza uma instância específica pelo ID.
    """

    def update(self, id: UUID | int, data: Dict, context: Dict) -> t_model:
        """
        Atualiza uma instância específica pelo ID.

        Args:
            id (UUID | int): Identificador da instância.
            data (Dict): Dados atualizados da instância.
            context (Dict): Contexto adicional para a operação.

        Returns:
            t_model: Instância atualizada do modelo.
        """
        model_repository = self.get_model_repository()
        return model_repository.update(id, **data)


class ServiceDeleteMixin:
    """
    Mixin para excluir instâncias de um modelo em um serviço.

    Métodos:
        delete: Exclui uma instância específica pelo ID.
    """

    def delete(self, id: UUID | int, context: Dict) -> None:
        """
        Exclui uma instância específica pelo ID.

        Args:
            id (UUID | int): Identificador da instância.
            context (Dict): Contexto adicional para a operação.

        Returns:
            None
        """
        model_repository = self.get_model_repository()
        return model_repository.delete(id)


class ContentTypeHandlerMixin:
    """
    Mixin para lidar com diferentes tipos de conteúdo em requisições HTTP.

    Métodos:
        parse_request_data: Analisa os dados da requisição com base no tipo de conteúdo.
    """

    def parse_request_data(self, request) -> Dict[str, Any]:
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
                return json.loads(request.body)
            except json.JSONDecodeError:
                raise ValueError("JSON inválido na requisição.")
        elif request.content_type.startswith("multipart/form-data"):
            data = request.POST.dict()
            files = {key: request.FILES[key] for key in request.FILES}
            return {**data, **files}
        else:
            raise ValueError("Formato de conteúdo não suportado.")


class ViewCreateModelMixin(ContentTypeHandlerMixin):
    """
    Mixin para ação de criação (`create`) em uma view baseada em classe.

    Métodos:
        post: Processa requisições POST para criar uma nova instância.
    """

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Processa requisições POST para criar uma nova instância.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da nova instância criada ou erros de validação.

        Raises:
            exceptions.BadRequest: Se os dados enviados forem inválidos ou ausentes.
        """
        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        self.verify_fields(data)

        context = self.get_context(request)
        obj = self.service.perform_action("create", data=data, context=context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=201)


class ViewRetrieveModelMixin:
    """
    Mixin para ações de leitura (`retrieve`) e listagem (`list`) em uma view baseada em classe.

    Métodos:
        retrieve: Obtém detalhes de uma única instância pelo ID.
        list: Lista múltiplas instâncias com paginação e filtros opcionais.
        get: Decide entre `retrieve` ou `list` com base na presença de um identificador.
    """

    def get_queryset(self, filter_kwargs: Optional[Dict[str, Any]] = None):
        """
        Retorna o queryset filtrado com base nos argumentos fornecidos.

        Args:
            filter_kwargs (Optional[Dict[str, Any]]): Dicionário contendo filtros opcionais.

        Returns:
            QuerySet: Queryset filtrado com base nos critérios fornecidos.
        """
        filter_kwargs = filter_kwargs or {}

        context = self.get_context(self.request)

        return self.service.perform_action(
            "list", filter_kwargs=filter_kwargs, context=context
        )

    def paginate_queryset(self, queryset, page_number):
        """
        Realiza a paginação básica do queryset com base no número da página.

        Args:
            queryset (QuerySet): Queryset a ser paginado.
            page_number (int): Número da página desejada.

        Returns:
            QuerySet: Subconjunto do queryset correspondente à página solicitada.

        Raises:
            ValueError: Se o número da página for inválido.
        """

        start = (page_number - 1) * self.paginate_by
        end = start + self.paginate_by

        return queryset[start:end]

    def retrieve(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Obtém os detalhes de uma única instância pelo ID.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da instância.

        Raises:
            exceptions.BadRequest: Se nenhum identificador for especificado.
        """
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        obj = self.get_object()
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)

    def list(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Lista múltiplas instâncias do modelo com suporte a paginação e filtros.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os resultados paginados e metadados de paginação.
        """
        filter_kwargs = request.GET.dict()
        queryset = self.get_queryset(filter_kwargs)
        page_number = int(request.GET.get("page", 1))

        paginated_queryset = self.paginate_queryset(
            queryset=queryset, page_number=page_number
        )

        serialized_data = [self.serialize_object(obj) for obj in paginated_queryset]

        response_data = {
            "pagination": {
                "current_page": page_number,
                "total_items": queryset.count(),
                "has_next": len(paginated_queryset) == self.paginate_by,
                "has_previous": page_number > 1,
            },
            "results": serialized_data,
        }

        return JsonResponse(response_data, status=200)

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Decide entre `retrieve` ou `list` com base na presença de um identificador.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da instância ou a lista de resultados.
        """
        obj_id = kwargs.get(self.lookup_field)

        if obj_id is not None:
            return self.retrieve(request, *args, **kwargs)

        return self.list(request, *args, **kwargs)


class ViewUpdateModelMixin(ContentTypeHandlerMixin):
    """
    Mixin para atualizar parcialmente ou completamente uma instância em uma view baseada em classe.

    Métodos:
        _update: Realiza a lógica de atualização da instância.
        patch: Atualiza parcialmente uma instância (requisição PATCH).
        put: Atualiza completamente uma instância (requisição PUT).
    """

    def _update(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Realiza a lógica de atualização de uma instância.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da instância atualizada.

        Raises:
            exceptions.BadRequest: Se nenhum identificador for especificado ou se os dados forem inválidos.
        """
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        context = self.get_context(request)
        obj = self.service.perform_action("update", obj_id, data=data, context=context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)

    def patch(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Atualiza parcialmente uma instância do modelo (requisição PATCH).

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da instância atualizada.
        """
        return self._update(request, *args, **kwargs)

    def put(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Atualiza completamente uma instância do modelo (requisição PUT).

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON contendo os dados da instância atualizada.

        Raises:
            exceptions.BadRequest: Se os campos obrigatórios não forem fornecidos ou forem inválidos.
        """
        data = json.loads(request.body)
        self.verify_fields(data)
        return self._update(request, *args, **kwargs)


class ViewDeleteModelMixin:
    """
    Mixin para excluir uma instância em uma view baseada em classe.

    Métodos:
       delete: Exclui uma instância do modelo pelo ID.
    """

    def delete(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        """
        Exclui uma instância do modelo pelo ID.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            *args: Argumentos adicionais.
            **kwargs: Argumentos nomeados adicionais.

        Returns:
            JsonResponse: Resposta JSON vazia com código HTTP 204 (No Content).

        Raises:
            exceptions.BadRequest: Se nenhum identificador for especificado.
        """
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        context = self.get_context(request)
        self.service.perform_action("delete", obj_id, context=context)

        return JsonResponse({}, status=204)
