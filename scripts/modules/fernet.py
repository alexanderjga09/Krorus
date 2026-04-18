import base64
import hashlib

from cryptography.fernet import Fernet


def derive_key_from_id(user_id: int) -> bytes:
    """Deriva una clave Fernet de 32 bytes a partir del ID de un usuario."""
    salt = b"discord_whisper_salt_v1"
    id_bytes = str(user_id).encode("utf-8")
    key = hashlib.pbkdf2_hmac("sha256", id_bytes, salt, 100000)
    return base64.urlsafe_b64encode(key)


def encrypt_message(message: str, recipient_id: int) -> str:
    """Cifra un mensaje usando el ID del destinatario como clave."""
    key = derive_key_from_id(recipient_id)
    f = Fernet(key)
    encrypted_data = f.encrypt(message.encode("utf-8"))
    return encrypted_data.decode("utf-8")


def decrypt_message(encrypted_message: str, recipient_id: int) -> str:
    """Descifra un mensaje usando el ID del destinatario como clave."""
    key = derive_key_from_id(recipient_id)
    f = Fernet(key)
    decrypted_data = f.decrypt(encrypted_message.encode("utf-8"))
    return decrypted_data.decode("utf-8")
