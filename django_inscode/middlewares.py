from django.http import JsonResponse

from .exceptions import APIException


class ExceptionHandlingMiddleware:
    """
    Middleware para capturar e processar exceções para o formato JSON.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as ex:
            return self.process_exception(request, ex)

    def process_exception(self, request, exception):
        """
        Processa diferentes tipos de exceções e retorna uma resposta JSON apropriada.
        """
        if isinstance(exception, APIException):
            return JsonResponse(exception.to_dict(), status=exception.status_code)

        return JsonResponse(
            {
                "code": 500,
                "message": "An unexpected error occurred.",
                "errors": [{"field": None, "message": str(exception)}],
            },
            status=500,
        )
