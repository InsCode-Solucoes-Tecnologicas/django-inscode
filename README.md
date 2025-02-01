# django-inscode

Django-inscode é um framework Django que tem como objetivo implementar um padrão de camadas baseado em serviços e repositórios para criação de projetos backend da empresa Inscode.

Este projeto fornece classes e funções personalizadas para:
- Modelos ORM
- Modelos de transporte
- Repositórios
- Serviços
- Views
- Permissões

## Modelos ORM
São fornecidos dois modelos bases possíveis de serem utilizados:
-  `BaseModel` -- Classe base com uma chave primária do tipo UUI4.
- `SoftDeleteBaseModel` -- Classe base com uma chave primária do tipo UUI4 e cujas instância são excluidas apenas logicamente (usando a flag is_deleted).

**Exemplo**

```
from django_inscode.models import SoftDeleteBaseModel
from django.db import models

class Book(SoftDeleteBaseModel):
  name = models.CharField(max_length=100)
```

## Modelos de transporte
Modelos de transporte irão servir como um guia para definir como objetos ORM serão serializados e retornados pela API. Para todo modelo do banco de dados deverá existir um modelo de transporte equivalente.

O django-inscode fornece suporte para dois tipos de objetos de transporte distintos: Um modelo interno chamado Transport e um Schema da biblioteca marshmallow. 

### Transport
Esta classe deverá ser descontinuada, porém para projetos que utilizam versões mais antigas do django-inscode ela é a única solução possível.

Para definir uma classe de transporte deve-se import a classe `Transport`.

**Exemplo**

```
from django_inscode.transports import Transport
from dataclasses import dataclass

@dataclass(frozen=True)
class BookTransport(Transport):
  name: str
```

## Marshmallow Schema
Esta é a classe de transporte recomendada para novos projetos em desenvolvimento que utilizam a biblioteca django-inscode.

**Exemplo**
```
from marshmallow import Schema, fields

class BookTransport(Schema):
  name = fields.Str()
```

## Repositórios
Repositórios são boas interfaces para garantir uma interação tranquila entre a aplicação e o banco de dados. Um repositório funciona criando e buscando dados no banco de dados e retornando objetos ORM relacionados.

Desse modo, ao utilizar a biblioteca django-inscode não se deve usar instâncias de objetos ORM, mas sim seus repositórios.

**Exemplo**
```
from django_inscode.repositories import Repository
from .models import Book

book_repository = Repository(Book)

book = book_repository.create(name="Novo livro") # Cria um novo livro
updated_book = book_repository.update(book.id, name="Novo livro atualizado") # Atualiza livro
retrieved_book = book_repository.read(book.id) # Retorna o livro
filtered_books = book_repository.filter(name="Novo livro atualizado") # Retorna todos os livros com o nome dado
all_books = book_repository.list_all() # Retorna todos os livros
book_repository.delete(book.id) # Exclui o livro
```

## Serviços
Serviços são utilizados para encapsular lógicas de negócios da aplicação. Um serviço pode ser do tipo `Model` ou do tipo `Orchestrator`.

Em uma arquitetura em camadas, um serviço depende de um ou mais repositórios para controlar suas ações.

### Serviços de modelo
Serviços de modelo são adequados para operações CRUD sobre modelos da aplicação. Na classe de serviço é possível validar dados de uma requisição e também sobrescrever métodos para lidar com lógicas de negócio personalizadas.

Para todo modelo criado, é necessário criar um repositório e uma classe de serviço para ele.

**Exemplo**
```
from django_inscode.services import ModelService
from django_inscode import exceptions

from .repositories import book_repository

class BookService(ModelService):
  def validate(self, data, instance):
    name = data.get("name")

    if name is not None and self.repository.filter(name=name).exists():
      raise exceptions.UnprocessableEntity(errors={"name": "Já existe um livro com este nome."})

  def create(self, data, context):
    # Adicionar, caso precise, alguma lógica de negócio
    return super().create(data, context)

  def read(self, data, context):
    # Adicionar, caso precise, alguma lógica de negócio
    return super().read(data, context)

  def update(self, data, context): 
    # Adicionar, caso precise, alguma lógica de negócio
    return super().update(data, context)

  def delete(self, data, context):
    # Adicionar, caso precise, alguma lógica de negócio
    return super().update(data, context)

book_service = BookService(book_repository)
```

No exemplo, `data` é um dicionário contendo os itens da requisição e `context` é um dicionário com informações adicionais da requisição HTTP como o usuário e a sessão.

**Exemplo**
```
from django_inscode.services import ModelService
from django_inscode import exceptions

class BookService(ModelService):
  def create(self, data, context):
    user = context["user"]
    session = context["session"]

    # Alguma lógica com user ou session

    return super().create(data, context)
```

Há também casos onde desejamos realizar apenas algumas ações sobre um modelo. Por exemplo, pode haver um caso em que seja desejado apenas ações de criar e ver modelos. Neste caso, utiliza-se a classe `GenericModelView` e define-se as ações desejadas com mixins.

**Exemplo**
from django_inscode.services import GenericModelService
from django_inscode import mixins

from .repositories import book_repository

class BookService(mixins.ServiceCreateMixin, mixins.ServiceReadMixin, GenericModelService):
  pass

book_service = BookService(book_repository) # Serviço com ações apenas de criar, ler e listar.

### Serviços orquestradores
Em muitas ocasiões é necessário realizar ações na API que não sejam relacionadas ao CRUD de algum modelo. É comum algumas lógicas de negócio que utilizem várias regras para retornar um resultado. Neste caso, é necessário utilizar serviços orquestradores.

Serviços orquestradores funcionam ao utilizar um ou vários repositórios para realizer uma ação na aplicação.

**Exemplo**
```
from django_inscode.services import OrchestratorService

import requests
import json

class EnviaNomesDosLivrosParaAPIExternaService(OrchestratorService):
  def execute(self, *args, **kwargs):
    # A lógica principal de um serviço orquestrador deve estar na função execute.
    url = "https://api.exemplo.com/endpoint"

    books = book_repository.list_all()
    books_names = list(map(lambda book: book.name, books))

    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(url, data=json.dumps(dados), headers=headers)

    if response.status_code == 200:
      return {"message": "Dados enviados com sucesso."}
    else:
      return {"message": "Erro ao enviar dados."}
```
Serviços orquestradores também podem receber dados de uma requisição e um contexto.

**Exemplo**
```
class AlgumOrquestradorService(OrchestratorService):
  def execute(self, *args, **kwargs):
    data = kwargs.get("data")
    context = kwargs.get("context")
    ...
```

Observação: Serviços orquestradores devem sempre retornar dicionários.

## Views
O django-inscode fornece views prontas para lidar com serviços orquestradores e serviços de modelo, sem precisar realizar configurações adicionais.

### Views de modelo
Views de modelo representam os endpoints para acessar os serviços de modelo.

**Exemplo**
```
from django_inscode.views import ModelView
from django_inscode.permissions import IsAuthenticated

from django_inscode.serializers import Serializer # Maneira antiga

from .models import Book
from .transports import BookTransport
from .services import BookService


class BookView(ModelView):
  fields = ["name"] # define os campos obrigatórios da requisição
  permissions = [IsAuthenticated] # define as permissões para acesso à view
  service = book_service # serviço que irá realizar as ações
  lookup_field = "id" # parâmetro de busca da url
  # serializer = Serializer(Book, BookTransport) !!!Maneira antiga usando a classe Transport!!!
  serializer = BookTransport # Maneira mais recente usando marshmallow e schema
```

Esta view irá fornecer de maneira automática os métodos de POST, GET (Retrieve), GET (List com paginação), PATCH, PUT e DELETE.

**Exemplo**
```
from .views import BookView

urlpatterns = [
  path("book/", BookView.as_view()),
  path("book/<pk:id>/", BookView.as_view())
]
```

Nos casos em que exitam serviços de modelo que possuam apenas algumas ações, como no exemplo do livro com apenas opções de create e retrieve, também é possível limitar estes acessos na própria view. Neste caso é necessário utilizar a classe `GenericModelView`

**Exemplo**
```
from django_inscode.views import GenericModelView
from django_inscode.permissions import IsAuthenticated
from django_inscode import mixins

from .models import Book
from .transports import BookTransport
from .services import BookService


class BookView(mixins.ViewCreateModelMixin, mixins.ViewRetrieveModelMixin, GenericModelView):
  fields = ["name"]
  permissions = [IsAuthenticated]
  service = book_service
  lookup_field = "id"
  serializer = BookTransport
```

### Views orquestradoras
Verificar

## Permissões
O django-inscode fornece a classe `BasePermission` para criar permissões customizadas para serem utilizadas em views.

Uma permissão pode atuar a nível de view e a nível de objeto.

**Exemplo**
```
from django_inscode.permissions import BasePermission

class IsAlgumaPermission(BasePermission):
  def has_permission(self, request, view):
    if request.user == ...
      return True
    else: 
      return False

  def has_object_permission(self, request, view, obj):
    # obj será o objeto da view (no caso de BookView, uma instancia de livro)
    # permissões a nivel de objeto são usadas em rotas que atuem em cima de um unico objeto
    # como no caso da rota /book/id/

    if obj.name == "oi" and not request.user.is_authenticated:
      return False
    else:
      return True
```