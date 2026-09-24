# tests/test_llm_router.py
import pytest
from services import llm_router
from services.llm_router import ChainEntry, extract_json, parse_llm_json

def test_parse_llm_json_plain():
    assert parse_llm_json('{"name": "A"}') == {"name": "A"}

def test_parse_llm_json_fenced():
    assert parse_llm_json('```json\n{"name":"A"}\n```') == {"name": "A"}

def test_parse_llm_json_list_first():
    assert parse_llm_json('[{"name":"A"},{"name":"B"}]') == {"name": "A"}

def test_parse_llm_json_garbage():
    assert parse_llm_json("not json at all") is None

@pytest.mark.asyncio
async def test_failover_to_second_provider(monkeypatch):
    calls = []
    async def fake_call(provider, model, key, system, user):
        calls.append(provider)
        if provider == "gemini":
            raise Exception("500 boom")
        return '{"name": "OK"}'
    monkeypatch.setattr(llm_router, "_call_provider", fake_call)
    monkeypatch.setattr(llm_router, "RETRY_BACKOFF", [0, 0, 0])
    llm_router._cache.cache.clear()
    chain = [
        ChainEntry(provider="gemini", model="m", api_key="k"),
        ChainEntry(provider="groq", model="m", api_key="k"),
    ]
    out = await extract_json(chain, "prompt")
    assert out == {"name": "OK"}
    assert calls[0] == "gemini"
    assert "groq" in calls

@pytest.mark.asyncio
async def test_empty_chain_returns_none():
    assert await extract_json([], "p") is None

@pytest.mark.asyncio
async def test_cache_hit(monkeypatch):
    calls = []
    async def fake_call(provider, model, key, system, user):
        calls.append(provider)
        return '{"name": "CACHED"}'
    monkeypatch.setattr(llm_router, "_call_provider", fake_call)
    monkeypatch.setattr(llm_router, "RETRY_BACKOFF", [0, 0, 0])
    llm_router._cache.cache.clear()
    chain = [ChainEntry(provider="groq", model="m", api_key="k")]
    a = await extract_json(chain, "same-prompt")
    b = await extract_json(chain, "same-prompt")
    assert a == b == {"name": "CACHED"}
    assert len(calls) == 1  # second served from cache
