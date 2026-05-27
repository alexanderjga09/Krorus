import asyncio
import json
import re
from pathlib import Path


def is_valid_domain(domain: str) -> bool:
    pattern = r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$"
    return re.match(pattern, domain) is not None


async def read_json(path: Path) -> list:
    try:
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        return json.loads(content)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        backup_path = path.with_suffix(".json.bak")
        try:
            await asyncio.to_thread(path.rename, backup_path)
        except Exception:
            pass
        return []


async def write_json(path: Path, data: list) -> None:
    content = json.dumps(data, indent=4, ensure_ascii=False)
    await asyncio.to_thread(path.write_text, content, encoding="utf-8")
