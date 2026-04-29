import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

KEYS_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "keysDB.json"


def derive_key_from_id(user_id: int) -> rsa.RSAPrivateKey:
    """Genera u obtiene el par de claves RSA persistiendo la información en un archivo JSON."""
    # Asegurar que el directorio data exista
    os.makedirs(os.path.dirname(KEYS_FILE_PATH), exist_ok=True)

    # Cargar base de datos de claves desde JSON
    keys_db = {}
    if os.path.exists(KEYS_FILE_PATH):
        with open(KEYS_FILE_PATH, "r") as f:
            try:
                keys_db = json.load(f)
            except json.JSONDecodeError:
                keys_db = {}

    user_id_str = str(user_id)

    if user_id_str in keys_db:
        # Cargar clave privada existente desde formato PEM
        private_key = serialization.load_pem_private_key(
            keys_db[user_id_str].encode("utf-8"), password=None
        )
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise TypeError("Loaded key is not an RSA private key")
        return private_key

    # Si no existe, generar una nueva clave
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Serializar la clave privada a PEM para guardarla en el JSON
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    keys_db[user_id_str] = pem.decode("utf-8")

    # Guardar la base de datos actualizada
    with open(KEYS_FILE_PATH, "w") as f:
        json.dump(keys_db, f, indent=4)

    return private_key


def encrypt_message(message: str, recipient_id: int) -> str:
    """Cifra un mensaje usando la clave pública del destinatario."""
    private_key = derive_key_from_id(recipient_id)
    public_key = private_key.public_key()

    encrypted_data = public_key.encrypt(
        message.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(encrypted_data).decode("utf-8")


def decrypt_message(encrypted_message: str, recipient_id: int) -> str:
    """Descifra un mensaje usando la clave privada del destinatario."""
    private_key = derive_key_from_id(recipient_id)

    decrypted_data = private_key.decrypt(
        base64.b64decode(encrypted_message.encode("utf-8")),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return decrypted_data.decode("utf-8")
