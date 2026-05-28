from unittest.mock import MagicMock

import discord
import pytest

from scripts.modules.message import GroqRateLimiter, Message


@pytest.fixture
def mock_message():
    msg = MagicMock(spec=discord.Message)
    msg.content = ""
    msg.author = MagicMock()
    msg.author.id = 0
    msg.author.roles = []
    msg.attachments = []
    msg.channel = MagicMock()
    msg.guild = MagicMock()
    msg.jump_url = ""
    msg.id = 0
    return Message(msg)


class TestGroqRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_allows_first_call(self):
        limiter = GroqRateLimiter(max_calls=5, window=60.0)
        await limiter.acquire()
        assert len(limiter._timestamps) == 1

    @pytest.mark.asyncio
    async def test_acquire_multiple_under_limit(self):
        limiter = GroqRateLimiter(max_calls=10, window=60.0)
        for _ in range(5):
            await limiter.acquire()
        assert len(limiter._timestamps) == 5

    def test_initial_timestamps_empty(self):
        limiter = GroqRateLimiter()
        assert limiter._timestamps == []


class TestMessageStaticMethods:
    def test_normalize_for_groq_removes_invisible(self):
        text = "H\u200bello\u200f World"
        result = Message._normalize_for_groq(text)
        assert result == "Hello World"

    def test_normalize_for_groq_preserves_normal(self):
        text = "Hello World"
        result = Message._normalize_for_groq(text)
        assert result == text

    def test_normalize_for_groq_nfc_normalization(self):
        text = "café"
        result = Message._normalize_for_groq(text)
        assert result == "café"

    def test_attachment_tipo_image(self):
        assert Message._attachment_tipo("image/png") == "Imagen"
        assert Message._attachment_tipo("image/jpeg") == "Imagen"
        assert Message._attachment_tipo("image/webp") == "Imagen"

    def test_attachment_tipo_video(self):
        assert Message._attachment_tipo("video/mp4") == "Video"
        assert Message._attachment_tipo("video/webm") == "Video"

    def test_attachment_tipo_audio(self):
        assert Message._attachment_tipo("audio/mpeg") == "Archivo"

    def test_attachment_tipo_generic(self):
        assert Message._attachment_tipo("application/pdf") == "Archivo"
        assert Message._attachment_tipo("text/plain") == "Archivo"

    def test_attachment_tipo_none(self):
        assert Message._attachment_tipo(None) == "Archivo"


class TestMessageInstanceMethods:
    def test_normalize_domain_lowercase(self, mock_message):
        result = mock_message._normalize_domain("Example.COM")
        assert result == "example.com"

    def test_normalize_domain_strips_www(self, mock_message):
        result = mock_message._normalize_domain("www.example.com")
        assert result == "example.com"

    def test_normalize_domain_no_www(self, mock_message):
        result = mock_message._normalize_domain("example.com")
        assert result == "example.com"

    def test_domain_matches_exact(self, mock_message):
        result = mock_message._domain_matches("example.com", ["example.com"])
        assert result is True

    def test_domain_matches_subdomain(self, mock_message):
        result = mock_message._domain_matches("sub.example.com", ["example.com"])
        assert result is True

    def test_domain_matches_no_match(self, mock_message):
        result = mock_message._domain_matches("other.com", ["example.com"])
        assert result is False

    def test_domain_matches_multiple_patterns(self, mock_message):
        result = mock_message._domain_matches("test.org", ["example.com", "test.org"])
        assert result is True

    def test_domain_matches_www(self, mock_message):
        result = mock_message._domain_matches("www.example.com", ["example.com"])
        assert result is True
