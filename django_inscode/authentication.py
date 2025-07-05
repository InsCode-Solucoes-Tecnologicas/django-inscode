from abc import ABC, abstractmethod

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .exceptions import Unauthorized


class BaseAuthentication(ABC):
    """
    Classe base para todos os mecanismos de autenticação.
    """

    @abstractmethod
    def authenticate(self, request):
        """
        Autentica a requisição e retorna um objeto de usuário.

        Deve retornar o usuário em caso de sucesso.
        Deve retornar None se o método de autenticação não se aplicar.
        Deve levantar uma exceção AuthenticationFailed se a autenticação falhar.
        """

    @abstractmethod
    def authenticate_header(self, request):
        """
        Retorna uma string que será usada no cabeçalho WWW-Authenticate
        para uma resposta 401 Unauthorized.
        """


class KeycloakBearerAuthentication(BaseAuthentication):
    """
    Valida um token Bearer OIDC (Keycloak) presente no cabeçalho Authorization,
    usando o backend OIDC configurado nos settings do projeto.
    """

    _oidc_backend = None

    def _get_oidc_backend(self):
        """
        Localiza, carrega e instancia o backend OIDC a partir de settings.AUTHENTICATION_BACKENDS.
        O resultado é armazenado em cache para requisições futuras.
        """
        if self._oidc_backend:
            return self._oidc_backend

        for backend_path in settings.AUTHENTICATION_BACKENDS:
            try:
                backend_class = import_string(backend_path)

                if issubclass(backend_class, OIDCAuthenticationBackend):
                    self.__class__._oidc_backend = backend_class()
                    return self._oidc_backend
            except ImportError:
                continue

        raise ImproperlyConfigured(
            "Nenhum backend de autenticação que herde de 'OIDCAuthenticationBackend' foi encontrado "
            "em settings.AUTHENTICATION_BACKENDS."
        )

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        oidc_backend = self._get_oidc_backend()

        try:
            claims = oidc_backend.get_userinfo(token, None, None)
            user = self.get_or_create_user(oidc_backend, claims)
            return user

        except Exception as e:
            raise Unauthorized("Token inválido ou expirado.")

    def get_or_create_user(self, backend, claims):
        """
        Busca ou cria um usuário Django com base nas claims do token.
        """
        user_qs = backend.filter_users_by_claims(claims)

        if user_qs.exists():
            return user_qs.first()

        return backend.create_user(claims)

    def authenticate_header(self, request):
        return "Bearer"
