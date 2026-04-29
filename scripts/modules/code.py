import secrets
import string


def generate_code() -> str:
    return "".join(secrets.choice(string.hexdigits) for _ in range(10))
