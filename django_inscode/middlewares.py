from django.http import JsonResponse

from .exceptions import APIException


class ExceptionHandlingMiddleware:
    """
    Middleware para capturar e processar exceções, retornando respostas no formato JSON.

    Este middleware intercepta exceções levantadas durante o processamento de uma requisição
    e as converte em respostas JSON apropriadas. Exceções personalizadas que herdam de
    `APIException` são tratadas com seus respectivos códigos de status e mensagens.
    Exceções inesperadas retornam um erro genérico com código HTTP 500.

    Attributes:
        get_response (callable): Função ou método que processa a requisição e retorna a resposta.
    """

    def __init__(self, get_response):
        """
        Inicializa o middleware com a função de processamento da requisição.

        Args:
            get_response (callable): Função ou método que processa a requisição.
        """
        self.get_response = get_response

    def __call__(self, request):
        """
        Processa a requisição capturando exceções, se ocorrerem.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.

        Returns:
            HttpResponse: Resposta gerada pelo processamento da requisição ou pela captura de uma exceção.
        """
        try:
            response = self.get_response(request)
            return response
        except Exception as ex:
            return self.process_exception(request, ex)

    def process_exception(self, request, exception):
        """
        Processa diferentes tipos de exceções e retorna uma resposta JSON apropriada.

        Se a exceção for uma instância de `APIException`, retorna os detalhes da exceção
        no formato JSON com o código de status correspondente. Para outras exceções,
        retorna uma mensagem genérica de erro com código HTTP 500.

        Args:
            request (HttpRequest): Objeto da requisição HTTP.
            exception (Exception): Exceção capturada durante o processamento da requisição.

        Returns:
            JsonResponse: Resposta JSON contendo os detalhes do erro.
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
