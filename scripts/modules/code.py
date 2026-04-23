import random
import string


def generate_code() -> str:
    return "".join(random.choices(string.hexdigits, k=10))
