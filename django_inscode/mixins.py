from uuid import UUID
from typing import Dict

from django.http import HttpRequest, JsonResponse

from .exceptions import BadRequest

import json


class ServiceCreateMixin:
    """Mixin para criar instâncias de um modelo em um serviço"""

    def create(self, data: Dict, context: Dict):
        model_repository = self.get_model_repository()
        return model_repository.create(**data)


class ServiceReadMixin:
    """Mixin para ler instâncias de um modelo em um serviço"""

    def read(self, id: UUID | int, context: Dict):
        model_repository = self.get_model_repository()
        return model_repository.read(id)

    def list_all(self, context: Dict):
        model_repository = self.get_model_repository()
        return model_repository.list_all()

    def filter(self, context: Dict, **kwargs):
        model_repository = self.get_model_repository()
        return model_repository.filter(**kwargs)


class ServiceUpdateMixin:
    """Mixin para atualizar instâncias de um modelo em um serviço"""

    def update(self, id: UUID | int, data: Dict, context: Dict):
        model_repository = self.get_model_repository()
        return model_repository.update(id, **data)


class ServiceDeleteMixin:
    """Mixin para excluir instâncias de um modelo em um serviço"""

    def delete(self, id: UUID | int, context: Dict):
        model_repository = self.get_model_repository()
        return model_repository.delete(id)


class ViewCreateModelMixin:
    """Mixin para ação de create em uma view."""

    def create(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        data = json.loads(request.body)
        self.verify_fields(data)
        context = self.get_context(request)

        obj = self.service.create(**data, **context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=201)


class ViewRetrieveModelMixin:
    """Mixin para ação de leitura em uma view."""

    def retrieve(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)
        if not obj_id:
            raise PermissionDenied("Nenhum identificador especificado.")

        obj = self.get_object()
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)


class ViewListModelMixin:
    """Mixin para listar instâncias com suporte a filtros e paginação em uma view."""

    def list(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
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


class ViewUpdateModelMixin:
    """Mixin para atualizar parcialmente uma instância em uma view."""

    def update(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)
        if not obj_id:
            raise PermissionDenied("Nenhum identificador especificado.")

        data = json.loads(request.body)
        self.verify_fields(data)
        context = self.get_context(request)

        obj = self.service.patch_by_id(obj_id=obj_id, **data, **context)
        serialized_obj = self.serialize_object(obj)

        return JsonResponse(serialized_obj, status=200)


class ViewDeleteModelMixin:
    """Mixin para excluir uma instância em uma view."""

    def delete(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        obj_id = kwargs.get(self.lookup_field)
        if not obj_id:
            raise PermissionDenied("Nenhum identificador especificado.")

        self.service.remove_by_id(obj_id=obj_id)

        return JsonResponse({}, status=204)
