from django.conf import settings as django_settings

from datetime import datetime

import settings
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
    Converte uma string em um objeto datetime com base no formato especificado.

    :param datetime_str: A string representando a data e hora.
    :return: Um objeto datetime convertido.
    :raises ValueError: Se a string não estiver no formato esperado.
    """
    try:
        _date = datetime.strptime(datetime_str, settings.DEFAULT_DATETIME_FORMAT)
        return _date
    except ValueError:
        raise ValueError(
            f"Erro ao converter '{datetime_str}' para datetime. "
            f"Certifique-se de que está no formato esperado: {settings.DEFAULT_DATETIME_FORMAT}"
        )
