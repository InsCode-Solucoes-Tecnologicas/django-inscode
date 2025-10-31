from django.http import JsonResponse
from django.conf import settings
from typing import Callable

from .exceptions import APIException


class ExceptionHandlingMiddleware:
    """
    Middleware para capturar exceções e convertê-las em respostas JSON no formato da API.

    Suporta uma API declarativa para mapear exceções do domínio para APIExceptions:
        ExceptionHandlingMiddleware.when(DomainError).then_raise(APIException(...))
        ExceptionHandlingMiddleware.when(ValueError).then_raise(lambda e: APIException(...))
    """

    exception_mappings: dict[type, Callable] = {}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as ex:
            return self.process_exception(request, ex)

    def process_exception(self, request, exception):
        """
        Transforma exceções conforme os mapeamentos registrados,
        e retorna JSONResponse apropriado.
        """
        for exc_type, transformer in self.exception_mappings.items():
            if isinstance(exception, exc_type):
                transformed = transformer(exception)

                if isinstance(transformed, APIException):
                    return JsonResponse(
                        transformed.to_dict(),
                        status=transformed.status_code,
                    )

                return transformed

        if isinstance(exception, APIException):
            return JsonResponse(exception.to_dict(), status=exception.status_code)

        return JsonResponse(
            {
                "message": "An unexpected error occurred.",
                "errors": {"message": str(exception)} if bool(settings.DEBUG) else {},
            },
            status=500,
        )

    @classmethod
    def when(cls, exc_type):
        return _ExceptionMapper(cls, exc_type)


class _ExceptionMapper:
    def __init__(self, middleware_cls, exc_type):
        self.middleware_cls = middleware_cls
        self.exc_type = exc_type

    def then_raise(self, value):
        """
        Registra um mapeamento de exceção para outra exceção (normalmente APIException).

        `value` pode ser:
          - uma instância de APIException (será retornada diretamente)
          - um callable que recebe a exceção original e retorna uma APIException
        """
        def transformer(exc):
            if callable(value):
                return value(exc)
            return value

        self.middleware_cls.exception_mappings[self.exc_type] = transformer
        return self.middleware_cls


__all__ = ["ExceptionHandlingMiddleware"]