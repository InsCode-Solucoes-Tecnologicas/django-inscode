from . import mixins
from .repositories import Repository

from typing import TypeVar, Dict
from abc import ABC, abstractmethod

T = TypeVar("T", bound=Repository)


class OrchestratorService(ABC):
    """
    Classe base para serviços orquestradores.

    Um serviço orquestrador realiza lógicas complexas que podem envolver múltiplos repositórios
    ou outros serviços para executar operações maiores na API. É ideal para operações que vão
    além do CRUD básico.

    Métodos:
        execute: Método abstrato para implementar a lógica principal do serviço.
    """

    @abstractmethod
    def execute(self, *args, **kwargs):
        """
        Executa o código principal do serviço.

        Este método deve ser implementado pelas subclasses para definir a lógica específica.

        Args:
            *args: Argumentos posicionais necessários para a execução.
            **kwargs: Argumentos nomeados adicionais.
        """
        pass


class GenericModelService:
    """
    Classe genérica para servir como base para serviços de modelos.

    Serviços de modelos lidam com a lógica CRUD de modelos, atuando em uma camada acima dos
    repositórios. Eles podem realizar validações e outras lógicas de negócio antes de interagir
    com o banco de dados.

    Attributes:
        repository (Repository): O repositório associado ao modelo.
    """

    def __init__(self, repository: T):
        """
        Inicializa o serviço com o repositório associado.

        Args:
            repository (Repository): O repositório do modelo que será utilizado pelo serviço.
        """
        self.repository = repository

    def get_model_repository(self):
        """
        Retorna o repositório associado ao modelo.

        Returns:
            Repository: O repositório associado ao modelo.
        """
        return self.repository

    def validate(self, data: Dict, instance=None):
        """
        Valida os dados fornecidos durante uma ação de criação ou atualização.

        Durante a criação, o argumento `instance` não estará disponível. Durante a atualização,
        `instance` será a instância em questão, permitindo validações adicionais baseadas no objeto.

        Args:
            data (Dict): Dados fornecidos para validação.
            instance (Model, optional): Instância em atualização (caso aplicável).

        Raises:
            ValidationError: Se os dados não forem válidos.
        """
        pass

    def perform_action(self, action: str, *args, **kwargs):
        """
        Executa uma ação no serviço de modelo.

        Este método é a interface principal para realizar operações no serviço,
        como criar, ler, atualizar ou excluir instâncias do modelo. Ele garante que
        validações sejam executadas antes das operações.

        Args:
            action (str): A ação a ser realizada (e.g., 'create', 'read', 'update', 'delete').
            *args: Argumentos posicionais necessários para a ação.
            **kwargs: Argumentos nomeados adicionais (e.g., 'data' para criação/atualização).

        Returns:
            Any: O resultado da operação correspondente.

        Raises:
            ValueError: Se a ação especificada não for reconhecida.
            ValidationError: Se os dados fornecidos forem inválidos.
            NotFound: Se o recurso solicitado não for encontrado.
            InternalServerError: Se ocorrer um erro inesperado durante a operação.
        """
        data = kwargs.get("data", {})
        filter_kwargs = kwargs.get("filter_kwargs", {})
        context = kwargs.get("context", {})

        if action == "create" and isinstance(self, mixins.ServiceCreateMixin):
            self.validate(data)
            return self.create(data, context)
        elif action == "read" and isinstance(self, mixins.ServiceReadMixin):
            return self.read(*args, context=context)
        elif action == "list_all" and isinstance(self, mixins.ServiceReadMixin):
            return self.list_all(context=context)
        elif action == "list" and isinstance(self, mixins.ServiceReadMixin):
            return self.list(context=context, **filter_kwargs)
        elif action == "update" and isinstance(self, mixins.ServiceUpdateMixin):
            instance = self.read(*args, context=context)
            self.validate(data, instance=instance)
            return self.update(*args, data=data, context=context)
        elif action == "delete" and isinstance(self, mixins.ServiceDeleteMixin):
            return self.delete(*args, context=context)
        else:
            raise ValueError(f"Ação desconhecida ou inválida: {action}")


class ModelService(
    GenericModelService,
    mixins.ServiceCreateMixin,
    mixins.ServiceReadMixin,
    mixins.ServiceUpdateMixin,
    mixins.ServiceDeleteMixin,
):
    """
    Serviço que fornece ações CRUD (criar, ler, atualizar e excluir) para um modelo.

    Esta classe é adequada para modelos simples que não necessitam de lógicas
    adicionais. Para casos mais complexos, os métodos podem ser sobrescritos.
    """

    pass
