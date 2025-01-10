from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Transport:
    """
    Classe base para definir objetos de transporte de dados.

    Um objeto de transporte é utilizado para representar os dados que serão serializados
    ou transferidos entre diferentes camadas da aplicação, como entre serviços e APIs.

    Attributes:
        id (UUID): Identificador único do objeto de transporte.
    """

    id: UUID
