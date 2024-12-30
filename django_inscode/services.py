from . import mixins
from .repositories import Repository

from typing import TypeVar, Dict
from abc import ABC, abstractmethod

T = TypeVar("T", bound=Repository)


class OrchestratorService(ABC):
    """
    Classe base para serviços orquestradores.

    Um serviço orquestrador consiste em um serviço genérico que realiza lógicas complexas
    na API. Isto é, não é um simples serviço de CRUD, mas sim um serviço que muitas vezes
    irá utilizar diversos repositórios ou outros serviços para realizar uma operação lógica
    maior na API.

    Você pode criar diversos métodos extras para a classe deste serviço, no entanto, o código
    principal deve estar presente no método execute deste serviço.
    """

    @abstractmethod
    def execute(self, *args, **kwargs):
        """Executa o código principal do serviço"""
        pass


class GenericModelService:
    """
    Classe genérica para servir como base para serviços de modelos.

    Serviços de modelos são serviços responsável por lidar com a lógica CRUD de modelos.

    Um serviço atua em uma camada acima do repositório, isto é, ela utiliza um repositório
    associado ao modelo ou multiplos repositórios para realizar ações de lógicas de negócio
    antes de performar uma ação no banco de dados.
    """

    def __init__(self, repository: T):
        self.repository = repository

    def get_model_repository(self):
        return self.repository


class ModelService(
    GenericModelService,
    mixins.ServiceCreateMixin,
    mixins.ServiceReadMixin,
    mixins.ServiceUpdateMixin,
    mixins.ServiceDeleteMixin,
):
    """
    Esta classe fornece todas as ações necessárias para criar, atualizar, ler e excluir
    um modelo de forma automática.

    Para modelos simples que não necessitam de nenhuma validação, esta classe irá fornecer
    tudo pronto.

    Caso o modelo precise de lógicas adicionais ou validações, você pode sobrescrever os métodos
    validate, create, read, list_all, filter e delete.
    """

    def validate(self, data: Dict, instance=None):
        """
        Método para validar os dados passados no corpo da requisição durante uma ação de
        criação ou atualização.

        Durante a ação de criação, o argumento 'instance' não estará disponível.

        Já, em uma ação de atualização, o argumento 'instance' estará acessível e será
        corresponde à instância em atualização em questão. Isso permite criar validações
        adicionais com base no objeto.
        """
        pass

    def perform_action(self, action: str, *args, **kwargs):
        """
        Executa uma ação no serviço de modelo.

        Este método é a interface principal para realizar operações no serviço,
        como criar, ler, atualizar ou excluir instâncias do modelo. Ele garante que
        validações sejam executadas antes das operações.

        Parâmetros:
            action (str): A ação a ser realizada (e.g., 'create', 'read', 'update', 'delete').
            *args: Argumentos posicionais necessários para a ação.
            **kwargs: Argumentos nomeados adicionais (e.g., 'data' para criação/atualização).

        Retorna:
            O resultado da operação correspondente.

        Levanta:
            ValueError: Se a ação especificada não for reconhecida.
        """
        data = kwargs.get("data", {})
        filter_kwargs = kwargs.get("filter_kwargs", {})
        context = kwargs.get("context", {})

        if action == "create":
            self.validate(data)
            return self.create(data, context)
        elif action == "read":
            return self.read(*args, context=context)
        elif action == "list_all":
            return self.list_all(context=context)
        elif action == "filter":
            return self.filter(context=context, **filter_kwargs)
        elif action == "update":
            instance = self.read(*args, context=context)
            self.validate(data, instance=instance)
            return self.update(*args, data=data, context=context)
        elif action == "delete":
            return self.delete(*args, context=context)
        else:
            raise ValueError(f"Ação desconhecida: {action}")
