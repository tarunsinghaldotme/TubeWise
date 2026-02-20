"""
test_config.py — Unit tests for config.py validation
"""

from __future__ import annotations

import os
import pytest

from config import Config


class TestConfigValidate:
    """Test Config.validate() method."""

    def test_validate_passes_when_all_set(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "us-east-1")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "secret_abc123")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "abc123def456")
        errors = Config.validate()
        assert errors == []

    def test_validate_fails_missing_notion_token(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "us-east-1")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "abc123def456")
        errors = Config.validate()
        assert any("NOTION_TOKEN" in e for e in errors)

    def test_validate_fails_missing_notion_page_id(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "us-east-1")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "secret_abc123")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "")
        errors = Config.validate()
        assert any("NOTION_PARENT_PAGE_ID" in e for e in errors)

    def test_validate_fails_missing_region(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "secret_abc123")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "abc123def456")
        errors = Config.validate()
        assert any("AWS_REGION" in e for e in errors)

    def test_validate_skip_notion(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "us-east-1")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "")
        errors = Config.validate(skip_notion=True)
        assert errors == []

    def test_validate_multiple_errors(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_REGION", "")
        monkeypatch.setattr(Config, "NOTION_TOKEN", "")
        monkeypatch.setattr(Config, "NOTION_PARENT_PAGE_ID", "")
        errors = Config.validate()
        assert len(errors) == 3


class TestConfigBearerToken:
    """Test bearer token auth detection."""

    def test_bearer_token_auth_when_set(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_BEARER_TOKEN_BEDROCK", "some-token")
        assert Config.is_bearer_token_auth() is True

    def test_no_bearer_token_auth_when_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "AWS_BEARER_TOKEN_BEDROCK", "")
        assert Config.is_bearer_token_auth() is False


class TestConfigDefaults:
    """Test that default values are sensible."""

    def test_default_chunk_size(self):
        assert Config.CHUNK_SIZE == 12000

    def test_default_chunk_overlap(self):
        assert Config.CHUNK_OVERLAP == 500

    def test_default_max_tokens(self):
        assert Config.MAX_TOKENS == 4096

    def test_default_temperature(self):
        assert Config.TEMPERATURE == 0.3

    def test_default_worker_count(self):
        assert Config.DEFAULT_WORKER_COUNT == 2
