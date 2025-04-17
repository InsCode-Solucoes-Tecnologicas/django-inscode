from typing import ClassVar


class APIException(Exception):
    """
    Classe base para todas as exceções personalizadas.

    Attributes:
        status_code (int): Código de status HTTP associado à exceção.
        default_message (str): Mensagem padrão da exceção.
        message (str): Mensagem personalizada da exceção.
        errors (list): Lista de erros específicos associados à exceção.
    """

    status_code: ClassVar[int] = 500
    default_message: ClassVar[str] = "A server error occurred."

    def __init__(self, message=None, status_code=None, errors=None):
        """
        Inicializa uma instância de APIException.

        Args:
            message (str, optional): Mensagem principal do erro. Se não fornecida, será usada a mensagem padrão.
            status_code (int, optional): Código HTTP associado ao erro. Se não fornecido, será usado o código padrão.
            errors (list, optional): Lista de erros específicos, como campos inválidos. Se não fornecida, será uma lista vazia.
        """
        self.message = message or self.default_message
        self.status_code = status_code or self.status_code
        self.errors = errors or []

    def to_dict(self):
        """
        Converte a exceção em um dicionário JSON no formato simplificado.

        Returns:
            dict: Dicionário contendo o código HTTP, a mensagem e os erros associados.
        """
        return {
            "code": self.status_code,
            "message": self.message,
            "errors": self.errors,
        }


class BadRequest(APIException):
    status_code = 400
    default_message = "Bad request."


class Unauthorized(APIException):
    status_code = 401
    default_message = "Unauthorized access."


class PaymentRequired(APIException):
    status_code = 402
    default_message = "Payment required."


class Forbidden(APIException):
    status_code = 403
    default_message = "Forbidden access."


class NotFound(APIException):
    status_code = 404
    default_message = "Resource not found."


class MethodNotAllowed(APIException):
    status_code = 405
    default_message = "Method not allowed on this resource."


class NotAcceptable(APIException):
    status_code = 406
    default_message = "Not acceptable response format."


class ProxyAuthenticationRequired(APIException):
    status_code = 407
    default_message = "Proxy authentication required."


class RequestTimeout(APIException):
    status_code = 408
    default_message = "Request timeout exceeded."


class Conflict(APIException):
    status_code = 409
    default_message = "Conflict with the current state of the resource."


class Gone(APIException):
    status_code = 410
    default_message = "Resource is no longer available (gone)."


class LengthRequired(APIException):
    status_code = 411
    default_message = "Length required for the request."


class PreconditionFailed(APIException):
    status_code = 412
    default_message = "Precondition failed for the request headers or conditions."


class PayloadTooLarge(APIException):
    status_code = 413
    default_message = "Payload too large to process."


class URITooLong(APIException):
    status_code = 414
    default_message = "URI too long to process."


class UnsupportedMediaType(APIException):
    status_code = 415
    default_message = "Unsupported media type in the request payload."


class RangeNotSatisfiable(APIException):
    status_code = 416
    default_message = "Requested range not satisfiable by the resource."


class ExpectationFailed(APIException):
    status_code = 417
    default_message = "Expectation failed for the request headers or conditions."


class MisdirectedRequest(APIException):
    status_code = 421
    default_message = "Misdirected request."


class UnprocessableEntity(APIException):
    status_code = 422
    default_message = "Unprocessable entity."


class Locked(APIException):
    status_code = 423
    default_message = "Resource is locked."


class FailedDependency(APIException):
    status_code = 424
    default_message = "Failed dependency."


class TooEarly(APIException):
    status_code = 425
    default_message = "Too early to process the request."


class UpgradeRequired(APIException):
    status_code = 426
    default_message = "Upgrade required to proceed."


class PreconditionRequired(APIException):
    status_code = 428
    default_message = "Precondition required for the request."


class TooManyRequests(APIException):
    status_code = 429
    default_message = "Too many requests sent in a given amount of time."


class RequestHeaderFieldsTooLarge(APIException):
    status_code = 431
    default_message = "Request header fields too large."


class UnavailableForLegalReasons(APIException):
    status_code = 451
    default_message = "Resource unavailable for legal reasons."


class InternalServerError(APIException):
    status_code = 500
    default_message = "Internal server error."
