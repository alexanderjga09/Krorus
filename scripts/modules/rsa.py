import base64
import json
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

logger = logging.getLogger(__name__)

KEYS_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "keysDB.json"


def derive_key_from_id(user_id: int) -> rsa.RSAPrivateKey:
    """Genera u obtiene el par de claves RSA persistiendo la información en un archivo JSON.

    La escritura se realiza de forma atómica y se intentan aplicar permisos restrictivos al fichero.
    """
    # Asegurar que el directorio data exista
    KEYS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Cargar base de datos de claves desde JSON
    keys_db = {}
    if KEYS_FILE_PATH.exists():
        try:
            content = KEYS_FILE_PATH.read_text(encoding="utf-8")
            if content.strip():
                keys_db = json.loads(content)
        except json.JSONDecodeError:
            # Si el JSON está corrupto, renombrar a backup y continuar con DB vacía
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
            # Fallback: generar nueva clave a continuación

    # Si no existe, generar una nueva clave
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Serializar la clave privada a PEM para guardarla en el JSON
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    keys_db[user_id_str] = pem.decode("utf-8")

    # Guardar la base de datos actualizada de forma atómica
    try:
        tmp = KEYS_FILE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(keys_db, indent=4), encoding="utf-8")
        tmp.replace(KEYS_FILE_PATH)
        try:
            # Intentar aplicar permisos restrictivos (funciona en POSIX)
            os.chmod(KEYS_FILE_PATH, 0o600)
        except Exception:
            # No crítico en Windows; ignorar si falla
            pass
    except Exception as e:
        logger.exception(f"Error al guardar keysDB: {e}")

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
