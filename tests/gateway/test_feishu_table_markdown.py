"""Tests for Feishu outbound markdown table routing."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from tests.gateway._plugin_adapter_loader import load_plugin_adapter

_adapter = load_plugin_adapter("feishu")

_TABLE = "| col A | col B |\n| ----- | ----- |\n| 1     | 2     |"


def _make_adapter() -> Any:
    adapter = _adapter.FeishuAdapter(PlatformConfig(enabled=True))
    adapter._client = object()
    return adapter


def _call_build_outbound_payload(
    content: str, *, prefer_post: bool = False,
) -> tuple[str, str]:
    inst = object.__new__(_adapter.FeishuAdapter)
    return inst._build_outbound_payload(content, prefer_post=prefer_post)


def test_markdown_table_uses_schema_2_interactive_card():
    msg_type, payload_str = _call_build_outbound_payload(_TABLE)

    assert msg_type == "interactive"
    assert json.loads(payload_str) == {
        "schema": "2.0",
        "config": {"width_mode": "fill"},
        "body": {
            "elements": [
                {"tag": "markdown", "content": _TABLE},
            ],
        },
    }


def test_prefer_post_does_not_override_table_card_routing():
    msg_type, payload_str = _call_build_outbound_payload(
        _TABLE, prefer_post=True,
    )

    assert msg_type == "interactive"
    assert json.loads(payload_str)["body"]["elements"][0]["content"] == _TABLE


def test_non_table_markdown_still_uses_post():
    msg_type, payload_str = _call_build_outbound_payload("## Heading")

    assert msg_type == "post"
    assert json.loads(payload_str)["zh_cn"]["content"] == [
        [{"tag": "md", "text": "## Heading"}],
    ]


def test_plain_text_still_uses_text():
    msg_type, payload_str = _call_build_outbound_payload("plain text")

    assert msg_type == "text"
    assert json.loads(payload_str) == {"text": "plain text"}


@pytest.mark.asyncio
async def test_send_uses_interactive_for_every_chunk_of_table_message():
    adapter = _make_adapter()
    chunks = [_TABLE, "continuation without its own markdown marker"]
    adapter.truncate_message = lambda *_args: chunks
    adapter._feishu_send_with_retry = AsyncMock(
        return_value=SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(message_id="msg_table"),
        ),
    )

    result = await adapter.send(
        "oc_table", f"{_TABLE}\ncontinuation without its own markdown marker",
    )

    assert result.success is True
    calls = adapter._feishu_send_with_retry.await_args_list
    assert [call.kwargs["msg_type"] for call in calls] == [
        "interactive", "interactive",
    ]
    cards = [json.loads(call.kwargs["payload"]) for call in calls]
    assert [card["body"]["elements"][0]["content"] for card in cards] == chunks
