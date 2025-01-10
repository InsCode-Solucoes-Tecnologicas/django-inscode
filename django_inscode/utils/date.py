from django.conf import settings as django_settings

from datetime import datetime, date

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
    Converte uma string ou objeto date em um objeto datetime com base no formato especificado.

    :param datetime_str: A string representando a data e hora ou um objeto date.
    :return: Um objeto datetime convertido.
    :raises ValueError: Se a string não estiver no formato esperado.
    :raises TypeError: Se o argumento não for uma string ou um objeto date.
    """
    if isinstance(datetime_str, date) and not isinstance(datetime_str, datetime):
        datetime_str = datetime_str.strftime("%Y-%m-%d 00:00:00")

    elif not isinstance(datetime_str, str):
        raise TypeError(
            f"O argumento deve ser uma string ou um objeto date, mas foi recebido: {type(datetime_str).__name__}"
        )

    try:
        _date = datetime.strptime(datetime_str, settings.DEFAULT_DATETIME_FORMAT)
        return _date
    except ValueError:
        raise ValueError(
            f"Erro ao converter '{datetime_str}' para datetime. "
            f"Certifique-se de que está no formato esperado: {settings.DEFAULT_DATETIME_FORMAT}"
        )
