import base64
import json
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

KEYS_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "keysDB.json"

RSA_KEY_SIZE = 2048
AES_NONCE_SIZE = 12


def derive_key_from_id(user_id: int) -> rsa.RSAPrivateKey:
    """Genera u obtiene el par de claves RSA persistiendo la información en un archivo JSON.

    La escritura se realiza de forma atómica y se intentan aplicar permisos restrictivos al fichero.
    """
    KEYS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    keys_db = {}
    if KEYS_FILE_PATH.exists():
        try:
            content = KEYS_FILE_PATH.read_text(encoding="utf-8")
            if content.strip():
                keys_db = json.loads(content)
        except json.JSONDecodeError:
            backup = KEYS_FILE_PATH.with_suffix(".json.bak")
            try:
                KEYS_FILE_PATH.replace(backup)
            except Exception as e:
                logger.exception(f"No se pudo respaldar keysDB corrupto: {e}")
            keys_db = {}
        except Exception as e:
            logger.exception(f"Error al leer keysDB: {e}")
            keys_db = {}

    user_id_str = str(user_id)

    if user_id_str in keys_db:
        try:
            private_pem = keys_db[user_id_str].encode("utf-8")
            private_key = serialization.load_pem_private_key(private_pem, password=None)
            if not isinstance(private_key, rsa.RSAPrivateKey):
                raise TypeError("Loaded key is not an RSA private key")
            return private_key
        except Exception as e:
            logger.exception(
                f"Error cargando la clave privada existente para {user_id}: {e}"
            )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_KEY_SIZE)

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    keys_db[user_id_str] = pem.decode("utf-8")

    try:
        tmp = KEYS_FILE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(keys_db, indent=4), encoding="utf-8")
        tmp.replace(KEYS_FILE_PATH)
        try:
            os.chmod(KEYS_FILE_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.exception(f"Error al guardar keysDB: {e}")

    return private_key


def encrypt_message(message: str, recipient_id: int) -> str:
    """Cifra un mensaje usando cifrado híbrido (AES-GCM + RSA-OAEP).

    Permite cifrar mensajes de cualquier longitud superando el límite de RSA puro.
    Formato: base64(rsa_encrypted_aes_key || nonce || aes_gcm_ciphertext)
    """
    private_key = derive_key_from_id(recipient_id)
    public_key = private_key.public_key()

    aes_key = os.urandom(32)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(AES_NONCE_SIZE)

    message_bytes = message.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, message_bytes, None)

    encrypted_aes_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    combined = encrypted_aes_key + nonce + ciphertext
    return base64.b64encode(combined).decode("utf-8")


def decrypt_message(encrypted_message: str, recipient_id: int) -> str:
    """Descifra un mensaje usando cifrado híbrido (AES-GCM + RSA-OAEP)."""
    private_key = derive_key_from_id(recipient_id)

    data = base64.b64decode(encrypted_message.encode("utf-8"))

    rsa_key_size_bytes = RSA_KEY_SIZE // 8
    encrypted_aes_key = data[:rsa_key_size_bytes]
    nonce = data[rsa_key_size_bytes : rsa_key_size_bytes + AES_NONCE_SIZE]
    ciphertext = data[rsa_key_size_bytes + AES_NONCE_SIZE :]

    aes_key = private_key.decrypt(
        encrypted_aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    aesgcm = AESGCM(aes_key)
    decrypted_data = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_data.decode("utf-8")
