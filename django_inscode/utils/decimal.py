from decimal import Decimal, ROUND_HALF_UP


def format_decimal(value: Decimal, decimal_places: int = 2) -> str:
    """
    Formata um número Decimal para o número especificado de casas decimais.

    :param value: O valor Decimal a ser formatado.
    :param decimal_places: O número de casas decimais desejadas (padrão é 2).
    :return: Uma string representando o número formatado.
    """
    quantizer = Decimal(f"1.{'0' * decimal_places}")
    rounded_value = value.quantize(quantizer, rounding=ROUND_HALF_UP)
    return f"{rounded_value:.{decimal_places}f}"
