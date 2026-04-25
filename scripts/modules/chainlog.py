# scripts/modules/chainlog.py
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ChainLog:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.chain: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        self.chain = json.loads(content)
                    else:
                        self.chain = []
            except (json.JSONDecodeError, FileNotFoundError):
                print(
                    f"[ChainLog] Archivo {self.filepath} corrupto o vacío. Se iniciará una nueva cadena."
                )
                self.chain = []
        else:
            self.chain = []

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.chain, f, indent=2, ensure_ascii=False)

    def _hash_block(
        self, index: int, timestamp: str, data: dict, previous_hash: str
    ) -> str:
        block_str = json.dumps(
            {
                "index": index,
                "timestamp": timestamp,
                "data": data,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(block_str.encode("utf-8")).hexdigest()

    def add_alert(self, user_id: str, code: str, reason: str, jump_url: str) -> str:
        index = len(self.chain)
        previous_hash = self.chain[-1]["hash"] if self.chain else "0" * 64
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {
            "block_type": "alert",
            "user_id": str(user_id),
            "code": code,
            "reason": reason,
            "jump_url": jump_url,
        }
        block_hash = self._hash_block(index, timestamp, data, previous_hash)
        block = {
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash,
            "hash": block_hash,
            "block_type": "alert",
        }
        self.chain.append(block)
        self._save()
        return block_hash

    def add_pardon(
        self, original_block_index: int, moderator_id: str, reason: str
    ) -> Optional[str]:
        if original_block_index >= len(self.chain):
            return None
        target = self.chain[original_block_index]
        if target.get("block_type", "alert") != "alert":
            return None
        if self.is_pardoned(original_block_index):
            return None

        index = len(self.chain)
        previous_hash = self.chain[-1]["hash"] if self.chain else "0" * 64
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {
            "block_type": "pardon",
            "original_index": original_block_index,
            "moderator_id": str(moderator_id),
            "reason": reason,
        }
        block_hash = self._hash_block(index, timestamp, data, previous_hash)
        block = {
            "index": index,
            "timestamp": timestamp,
            "data": data,
            "previous_hash": previous_hash,
            "hash": block_hash,
            "block_type": "pardon",
        }
        self.chain.append(block)
        self._save()
        return block_hash

    def is_pardoned(self, block_index: int) -> bool:
        for block in self.chain:
            if (
                block.get("data", {}).get("block_type") == "pardon"
                and block["data"].get("original_index") == block_index
            ):
                return True
        return False

    def get_pardon_info(self, block_index: int) -> Optional[Dict[str, Any]]:
        for block in self.chain:
            if (
                block.get("data", {}).get("block_type") == "pardon"
                and block["data"].get("original_index") == block_index
            ):
                return block
        return None

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        return [
            block
            for i, block in enumerate(self.chain)
            if block.get("block_type", "alert") == "alert" and not self.is_pardoned(i)
        ]

    def verify_chain(self) -> bool:
        for i, block in enumerate(self.chain):
            if block["index"] != i:
                return False
            previous_hash = self.chain[i - 1]["hash"] if i > 0 else "0" * 64
            expected_hash = self._hash_block(
                block["index"],
                block["timestamp"],
                block["data"],
                block["previous_hash"],
            )
            if block["hash"] != expected_hash:
                return False
            if block["previous_hash"] != previous_hash:
                return False
        return True

    def last_hash(self) -> Optional[str]:
        return self.chain[-1]["hash"] if self.chain else None

    # ─── Métodos para los cogs ─────────────────────────────────
    def get_alerts_by_user(
        self, include_pardoned: bool = False
    ) -> Dict[str, List[Dict]]:
        """Devuelve un diccionario {user_id: [bloques de alerta]}.
        Si include_pardoned=False, omite las alertas perdonadas.
        """
        result: Dict[str, List[Dict]] = {}
        for i, block in enumerate(self.chain):
            if block.get("block_type") != "alert":
                continue
            if not include_pardoned and self.is_pardoned(i):
                continue
            uid = block["data"].get("user_id")
            if uid is None:
                continue
            result.setdefault(uid, []).append(block)
        return result

    def list_users(self) -> List[Tuple[str, int]]:
        """Retorna lista de (user_id, número de alertas activas) para el comando list-users."""
        alerts_by_user = self.get_alerts_by_user(include_pardoned=False)
        return [(uid, len(blocks)) for uid, blocks in alerts_by_user.items()]

    def get_user_alerts(
        self, user_id: str, include_pardoned: bool = False
    ) -> List[Dict]:
        """Devuelve todos los bloques de alerta de un usuario, con o sin perdonadas."""
        alerts_by_user = self.get_alerts_by_user(include_pardoned=include_pardoned)
        return alerts_by_user.get(str(user_id), [])

    def find_alert_index_by_code(
        self, code: str, only_active: bool = True
    ) -> Optional[int]:
        """
        Busca un bloque de tipo 'alert' con el código dado.
        Si only_active es True, solo devuelve el índice si no está perdonado.
        Retorna el índice (int) o None si no se encuentra.
        """
        for i, block in enumerate(self.chain):
            if block.get("block_type") != "alert":
                continue
            if block["data"].get("code") == code:
                if only_active and self.is_pardoned(i):
                    continue
                return i
        return None
