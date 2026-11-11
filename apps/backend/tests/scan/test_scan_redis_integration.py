"""Integration coverage for the scan Lua scripts against a real Redis server.

Set ``FACE_MATCH_TEST_REDIS_URL`` to an expendable Redis database.  Every test
uses UUID-namespaced keys and removes only keys from its own namespace.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib
import importlib.util
import json
import os
import sys
from threading import Barrier
import time
from types import ModuleType
from uuid import uuid4

import pytest
import redis


pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    url = os.environ.get("FACE_MATCH_TEST_REDIS_URL")
    if not url:
        pytest.skip("FACE_MATCH_TEST_REDIS_URL is not configured")
    return url


@pytest.fixture
def tasks_module(test_redis_url: str, monkeypatch: pytest.MonkeyPatch):
    """Import the public scripts without requiring the native face stack."""
    if importlib.util.find_spec("face_recognition") is None:
        ai_service = ModuleType("app.services.ai_service")

        def unused_face_operation(*args, **kwargs):
            raise AssertionError("Redis integration tests must not run face recognition")

        ai_service.get_face_encodings = unused_face_operation
        ai_service.compare_faces = unused_face_operation
        monkeypatch.setitem(sys.modules, "app.services.ai_service", ai_service)
        sys.modules.pop("app.workers.tasks", None)

    return importlib.import_module("app.workers.tasks")


@pytest.fixture
def redis_client(test_redis_url: str):
    client = redis.Redis.from_url(test_redis_url, decode_responses=True)
    client.ping()
    yield client
    client.close()


@pytest.fixture
def scan_namespace(redis_client: redis.Redis):
    prefix = f"face-match-it:{uuid4()}:"
    keys = {
        "remaining": f"{prefix}scan_remaining",
        "status": f"{prefix}scan_status",
        "processed": f"{prefix}scan_processed",
        "sequence": f"{prefix}scan_sequence",
        "events": f"{prefix}scan_events",
        "updates": f"{prefix}scan_updates",
    }
    yield prefix, keys

    owned_keys = list(redis_client.scan_iter(match=f"{prefix}*"))
    if owned_keys:
        redis_client.delete(*owned_keys)


def _event_keys(keys: dict[str, str]) -> tuple[str, ...]:
    return (
        keys["remaining"],
        keys["status"],
        keys["processed"],
        keys["sequence"],
        keys["events"],
        keys["updates"],
    )


def _claim_keys(keys: dict[str, str], claim_key: str) -> tuple[str, ...]:
    return (
        keys["processed"],
        claim_key,
        keys["remaining"],
        keys["sequence"],
        keys["events"],
        keys["status"],
    )


def _wait_for_messages(pubsub, count: int) -> list[str]:
    messages = []
    deadline = time.monotonic() + 3
    while len(messages) < count and time.monotonic() < deadline:
        message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if message and message["type"] == "message":
            messages.append(message["data"])
    return messages


def _assert_live_ttl(client: redis.Redis, key: str, maximum: int) -> None:
    ttl = client.ttl(key)
    assert 0 < ttl <= maximum, f"expected a live TTL for {key}, got {ttl}"


def test_public_lua_scripts_compile_and_scan_events_are_monotonic(
    redis_client, tasks_module, scan_namespace
):
    _, keys = scan_namespace
    scripts = (
        tasks_module.SCAN_EVENT_LUA,
        tasks_module.CLAIM_FILE_LUA,
        tasks_module.RELEASE_CLAIM_LUA,
        tasks_module.FINALIZE_FILE_LUA,
        tasks_module.TOKEN_EXPIRED_LUA,
        tasks_module.FAIL_SCAN_LUA,
    )
    shas = [redis_client.script_load(script) for script in scripts]
    assert redis_client.script_exists(*shas) == [True] * len(shas)

    redis_client.set(keys["remaining"], 3)
    redis_client.set(keys["status"], "running")
    redis_client.sadd(keys["processed"], "already-processed")

    pubsub = redis_client.pubsub()
    pubsub.subscribe(keys["updates"])
    subscription = pubsub.get_message(ignore_subscribe_messages=False, timeout=1)
    assert subscription is not None and subscription["type"] == "subscribe"

    persisted = []
    try:
        for event_type in ("started", "progress", "match"):
            encoded = redis_client.evalsha(
                shas[0],
                6,
                keys["sequence"],
                keys["events"],
                keys["updates"],
                keys["remaining"],
                keys["status"],
                keys["processed"],
                json.dumps({"type": event_type}),
                60,
            )
            persisted.append(encoded)

        published = _wait_for_messages(pubsub, 3)
    finally:
        pubsub.close()

    assert published == persisted
    events = [json.loads(raw) for raw in redis_client.lrange(keys["events"], 0, -1)]
    assert [event["type"] for event in events] == ["started", "progress", "match"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert redis_client.get(keys["sequence"]) == "3"
    assert redis_client.type(keys["sequence"]) == "string"
    assert redis_client.type(keys["events"]) == "list"
    for key in (
        keys["sequence"],
        keys["events"],
        keys["remaining"],
        keys["status"],
        keys["processed"],
    ):
        _assert_live_ttl(redis_client, key, 60)


def test_finalize_is_atomic_with_one_completed_terminal(
    redis_client, tasks_module, scan_namespace
):
    _, keys = scan_namespace
    file_count = 24
    redis_client.set(keys["remaining"], file_count)

    def finalize(index: int):
        payload = json.dumps({"type": "progress", "file_id": f"file-{index}"})
        return redis_client.eval(
            tasks_module.FINALIZE_FILE_LUA,
            6,
            *_event_keys(keys),
            f"file-{index}",
            payload,
            60,
            "integration-scan",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(finalize, range(file_count)))

    events = [json.loads(raw) for raw in redis_client.lrange(keys["events"], 0, -1)]
    terminal_events = [event for event in events if event["type"] == "completed"]
    assert len(events) == file_count + 1
    assert len(terminal_events) == 1
    assert terminal_events[0]["scan_id"] == "integration-scan"
    assert sorted(event["sequence"] for event in events) == list(range(1, file_count + 2))
    assert sum(outcome[0] == "completed" for outcome in outcomes) == 1
    assert redis_client.get(keys["remaining"]) == "0"
    assert redis_client.get(keys["status"]) == "completed"
    assert redis_client.get(keys["sequence"]) == str(file_count + 1)
    assert redis_client.scard(keys["processed"]) == file_count
    assert redis_client.type(keys["remaining"]) == "string"
    assert redis_client.type(keys["status"]) == "string"
    assert redis_client.type(keys["processed"]) == "set"

    after_terminal = finalize(0)
    assert after_terminal == ["exhausted_counter", "0"]
    assert redis_client.llen(keys["events"]) == file_count + 1


def test_token_expiration_is_unique_and_suppresses_later_results(
    redis_client, tasks_module, scan_namespace
):
    _, keys = scan_namespace
    redis_client.set(keys["remaining"], 3)
    expiration = json.dumps({"type": "token_expired", "scan_id": "integration-scan"})

    first = redis_client.eval(
        tasks_module.TOKEN_EXPIRED_LUA,
        6,
        *_event_keys(keys),
        "file-a",
        expiration,
        60,
    )
    later_result = redis_client.eval(
        tasks_module.FINALIZE_FILE_LUA,
        6,
        *_event_keys(keys),
        "file-b",
        json.dumps({"type": "match", "file_id": "file-b"}),
        60,
        "integration-scan",
    )
    second_expiration = redis_client.eval(
        tasks_module.TOKEN_EXPIRED_LUA,
        6,
        *_event_keys(keys),
        "file-c",
        expiration,
        60,
    )

    events = [json.loads(raw) for raw in redis_client.lrange(keys["events"], 0, -1)]
    assert first == ["token_expired", "2"]
    assert later_result == ["token_expired", "1"]
    assert second_expiration == ["terminal_exists", "0"]
    assert [event["type"] for event in events] == ["token_expired"]
    assert [event["sequence"] for event in events] == [1]
    assert redis_client.get(keys["status"]) == "token_expired"
    assert redis_client.get(keys["remaining"]) == "0"
    assert redis_client.get(keys["sequence"]) == "1"
    assert redis_client.smembers(keys["processed"]) == {"file-a", "file-b", "file-c"}


def test_concurrent_duplicate_failures_publish_one_failed_terminal(
    redis_client, tasks_module, scan_namespace
):
    _, keys = scan_namespace
    payload = json.dumps(
        {
            "type": "error",
            "scan_id": "integration-scan",
            "status": "failed",
            "error": "scan coordination state expired",
        }
    )
    start = Barrier(2)

    def fail_once(_call_number: int):
        start.wait()
        return redis_client.eval(
            tasks_module.FAIL_SCAN_LUA,
            4,
            keys["status"],
            keys["sequence"],
            keys["events"],
            keys["updates"],
            payload,
            60,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(fail_once, range(2)))

    events = [json.loads(raw) for raw in redis_client.lrange(keys["events"], 0, -1)]
    assert outcomes == ["failed", "failed"]
    assert events == [
        {
            "type": "error",
            "scan_id": "integration-scan",
            "status": "failed",
            "error": "scan coordination state expired",
            "sequence": 1,
        }
    ]
    assert redis_client.get(keys["status"]) == "failed"
    assert redis_client.get(keys["sequence"]) == "1"
    assert redis_client.llen(keys["events"]) == 1
    for key in (keys["status"], keys["sequence"], keys["events"]):
        _assert_live_ttl(redis_client, key, 60)


def test_claim_processed_release_and_ttls_use_real_redis_types(
    redis_client, tasks_module, scan_namespace
):
    prefix, keys = scan_namespace
    claim_key = f"{prefix}scan_claim:file-a"
    redis_client.set(keys["remaining"], 2)
    redis_client.set(keys["sequence"], 0)
    redis_client.rpush(keys["events"], json.dumps({"type": "seed"}))
    redis_client.set(keys["status"], "running")
    redis_client.sadd(keys["processed"], "file-z")

    claim_keys = _claim_keys(keys, claim_key)
    claimed = redis_client.eval(
        tasks_module.CLAIM_FILE_LUA,
        6,
        *claim_keys,
        "file-a",
        "worker-token",
        15,
        60,
    )
    duplicate_claim = redis_client.eval(
        tasks_module.CLAIM_FILE_LUA,
        6,
        *claim_keys,
        "file-a",
        "other-worker",
        15,
        60,
    )

    assert claimed == 1 and isinstance(claimed, int)
    assert duplicate_claim == -1 and isinstance(duplicate_claim, int)
    assert redis_client.get(claim_key) == "worker-token"
    assert redis_client.type(claim_key) == "string"
    _assert_live_ttl(redis_client, claim_key, 15)
    for key in (
        keys["remaining"],
        keys["sequence"],
        keys["events"],
        keys["status"],
        keys["processed"],
    ):
        _assert_live_ttl(redis_client, key, 60)

    assert redis_client.eval(tasks_module.RELEASE_CLAIM_LUA, 1, claim_key, "wrong-token") == 0
    assert redis_client.exists(claim_key) == 1
    assert redis_client.eval(tasks_module.RELEASE_CLAIM_LUA, 1, claim_key, "worker-token") == 1
    assert redis_client.exists(claim_key) == 0

    redis_client.sadd(keys["processed"], "file-a")
    already_processed = redis_client.eval(
        tasks_module.CLAIM_FILE_LUA,
        6,
        *claim_keys,
        "file-a",
        "third-worker",
        15,
        60,
    )
    assert already_processed == 0
    assert redis_client.type(keys["processed"]) == "set"
    assert redis_client.smembers(keys["processed"]) == {"file-a", "file-z"}
