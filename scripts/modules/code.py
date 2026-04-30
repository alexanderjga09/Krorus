import secrets


def generate_code() -> str:
    # Genera 10 caracteres hexadecimales utilizando secrets.token_hex
    return secrets.token_hex(5)
