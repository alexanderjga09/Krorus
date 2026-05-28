import re

from modules.code import generate_code


def test_generate_code_length():
    code = generate_code()
    assert len(code) == 10


def test_generate_code_hex():
    code = generate_code()
    assert re.fullmatch(r"[0-9a-f]{10}", code)


def test_generate_code_unique():
    codes = {generate_code() for _ in range(100)}
    assert len(codes) == 100


def test_generate_code_type():
    code = generate_code()
    assert isinstance(code, str)
