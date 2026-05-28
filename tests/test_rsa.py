import pytest

from scripts.modules.rsa import decrypt_message, derive_key_from_id, encrypt_message


@pytest.fixture(autouse=True)
def _isolate_keys_db(monkeypatch, tmp_path):
    """Use a temporary keysDB so tests don't touch the real one."""
    fake_path = tmp_path / "keysDB.json"
    monkeypatch.setattr("modules.rsa.KEYS_FILE_PATH", fake_path)


def test_derive_key_from_id_returns_rsa_key():
    key = derive_key_from_id(12345)
    assert hasattr(key, "public_key")
    assert hasattr(key, "decrypt")
    assert hasattr(key, "sign")


def test_derive_key_is_stable():
    key1 = derive_key_from_id(99999)
    key2 = derive_key_from_id(99999)
    from cryptography.hazmat.primitives import serialization

    pub1 = key1.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub2 = key2.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert pub1 == pub2


def test_derive_key_different_ids():
    key1 = derive_key_from_id(1)
    key2 = derive_key_from_id(2)
    from cryptography.hazmat.primitives import serialization

    pub1 = key1.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub2 = key2.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    assert pub1 != pub2


def test_encrypt_decrypt_roundtrip():
    user_id = 42
    original = "Hello, this is a secret message!"
    encrypted = encrypt_message(original, user_id)
    assert encrypted != original
    decrypted = decrypt_message(encrypted, user_id)
    assert decrypted == original


def test_encrypt_decrypt_long_message():
    user_id = 999
    original = "A" * 10000
    encrypted = encrypt_message(original, user_id)
    decrypted = decrypt_message(encrypted, user_id)
    assert decrypted == original


def test_encrypt_decrypt_unicode():
    user_id = 77
    original = "Héllo Wörld 🌍🔥 こんにちは"
    encrypted = encrypt_message(original, user_id)
    decrypted = decrypt_message(encrypted, user_id)
    assert decrypted == original


def test_decrypt_wrong_user_fails():
    original = "secret"
    encrypted = encrypt_message(original, 100)
    with pytest.raises(Exception):
        decrypt_message(encrypted, 200)


def test_encrypted_output_is_base64():
    encrypted = encrypt_message("test", 1)
    import base64

    try:
        base64.b64decode(encrypted)
    except Exception:
        pytest.fail("Output is not valid base64")
