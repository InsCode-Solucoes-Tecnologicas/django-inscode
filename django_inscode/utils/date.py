from django.conf import settings as django_settings

from datetime import datetime

from django_inscode import settings
import pytz


def get_actual_datetime() -> datetime:
    """
    Retorna um objeto datetime baseado no momento atual em que ele foi chamado e com base
    no fusohorário definido nas configurações do Django.

    :return: Um objeto datetime.
    """
    tz = pytz.timezone(django_settings.TIME_ZONE)
    return datetime.now(tz=tz)


def parse_str_to_datetime(datetime_str: str) -> datetime:
    """
    Converte uma string representando data e hora em um objeto datetime válido.

    :param datetime_str: A string representando a data no formato 'YYYY-MM-DD' ou 'YYYY-MM-DD HH:MM:SS'.
    :return: Um objeto datetime convertido.
    :raises ValueError: Se a string não estiver no formato esperado.
    """
    if not isinstance(datetime_str, str):
        raise TypeError(
            f"O argumento deve ser uma string, mas foi recebido: {type(datetime_str).__name__}"
        )

    try:
        # Tenta analisar o formato com data e hora
        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            # Se falhar, tenta apenas a data e adiciona 00:00:00
            return datetime.strptime(datetime_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Erro ao converter '{datetime_str}' para datetime. "
                "Certifique-se de que está no formato 'YYYY-MM-DD' ou 'YYYY-MM-DD HH:MM:SS'."
            )
