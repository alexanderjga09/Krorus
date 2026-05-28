import json

import pytest

from scripts.modules.utils import is_valid_domain, read_json, write_json


class TestIsValidDomain:
    def test_valid_domains(self):
        assert is_valid_domain("example.com")
        assert is_valid_domain("sub.domain.org")
        assert is_valid_domain("my-site.net")
        assert is_valid_domain("a.co")

    def test_invalid_domains(self):
        assert not is_valid_domain("")
        assert not is_valid_domain("not-a-domain")
        assert not is_valid_domain(".com")
        assert not is_valid_domain("example.")
        assert not is_valid_domain("http://example.com")
        assert not is_valid_domain("example..com")


class TestReadJson:
    @pytest.mark.asyncio
    async def test_read_valid_json(self, tmp_data_dir, sample_json_data):
        path = tmp_data_dir / "test.json"
        path.write_text(json.dumps(sample_json_data), encoding="utf-8")
        result = await read_json(path)
        assert result == sample_json_data

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tmp_data_dir):
        path = tmp_data_dir / "nonexistent.json"
        result = await read_json(path)
        assert result == []

    @pytest.mark.asyncio
    async def test_read_invalid_json(self, tmp_data_dir):
        path = tmp_data_dir / "invalid.json"
        path.write_text("not json", encoding="utf-8")
        result = await read_json(path)
        assert result == []

    @pytest.mark.asyncio
    async def test_read_non_list_json_returns_raw(self, tmp_data_dir):
        path = tmp_data_dir / "object.json"
        path.write_text('{"key": "value"}', encoding="utf-8")
        result = await read_json(path)
        assert result == {"key": "value"}


class TestWriteJson:
    @pytest.mark.asyncio
    async def test_write_json(self, tmp_data_dir, sample_json_data):
        path = tmp_data_dir / "output.json"
        await write_json(path, sample_json_data)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert json.loads(content) == sample_json_data

    @pytest.mark.asyncio
    async def test_write_and_read_back(self, tmp_data_dir):
        data = ["a", "b", "c"]
        path = tmp_data_dir / "roundtrip.json"
        await write_json(path, data)
        result = await read_json(path)
        assert result == data
