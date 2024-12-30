from uuid import UUID
from typing import Dict, Any, TypeVar

from django.http import HttpRequest, JsonResponse
from django.db.models import QuerySet, Model

import exceptions
import json

t_model = TypeVar("t_model", bound=Model)


class ServiceCreateMixin:
    """Mixin para criar instâncias de um modelo em um serviço"""

    def create(self, data: Dict, context: Dict) -> t_model:
        model_repository = self.get_model_repository()
        return model_repository.create(**data)


class ServiceReadMixin:
    """Mixin para ler instâncias de um modelo em um serviço"""

    def read(self, id: UUID | int, context: Dict) -> t_model:
        model_repository = self.get_model_repository()
        return model_repository.read(id)

    def list(self, context: Dict, **kwargs) -> QuerySet[t_model]:
        model_repository = self.get_model_repository()
        return model_repository.filter(**kwargs)


class ServiceUpdateMixin:
    """Mixin para atualizar instâncias de um modelo em um serviço"""

    def update(self, id: UUID | int, data: Dict, context: Dict) -> t_model:
        model_repository = self.get_model_repository()
        return model_repository.update(id, **data)


class ServiceDeleteMixin:
    """Mixin para excluir instâncias de um modelo em um serviço"""

    def delete(self, id: UUID | int, context: Dict) -> None:
        model_repository = self.get_model_repository()
        return model_repository.delete(id)


class ContentTypeHandlerMixin:
    """Mixin para lidar com diferentes tipos de conteúdo."""

    def parse_request_data(self, request) -> Dict[str, Any]:
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
    """Mixin para ação de create em uma view."""

    def post(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        self.verify_fields(data)

        context = self.get_context(request)
        obj = self.service.perfom_action("create", data=data, context=context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=201)


class ViewRetrieveModelMixin:
    """Mixin para ação de leitura e listagem em uma view."""

    def retrieve(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        obj = self.get_obj()
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)

    def list(self, request: HttpRequest, *args, **kwargs):
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
        obj_id = kwargs.get(self.lookup_field)

        if obj_id is not None:
            return self.retrieve(request, *args, **kwargs)

        return self.list(request, *args, **kwargs)


class ViewUpdateModelMixin(ContentTypeHandlerMixin):
    """Mixin para atualizar parcialmente uma instância em uma view."""

    def _update(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")
        try:
            data = self.parse_request_data(request)
        except ValueError as e:
            raise exceptions.BadRequest(errors=str(e))

        context = self.get_context()
        obj = self.service.perform_action("update", obj_id, data=data, context=context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)

    def patch(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        return self._update(request, *args, **kwargs)

    def put(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        data = json.loads(request.body)
        self.verify_fields(data)
        return self._update(request, *args, **kwargs)


class ViewDeleteModelMixin:
    """Mixin para excluir uma instância em uma view."""

    def delete(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)

        if not obj_id:
            raise exceptions.BadRequest("Nenhum identificador especificado.")

        context = self.get_context()
        self.service.perform_action("delete", obj_id, context=context)

        return JsonResponse({}, status=204)
