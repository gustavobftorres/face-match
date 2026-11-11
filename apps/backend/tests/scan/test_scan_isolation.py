import asyncio
import json

from fastapi import WebSocketDisconnect

from app.api import endpoints
from app.workers import tasks


class FakeScanRedis:
    """Small atomic model of the scan-specific Redis scripts used at the boundary."""

    def __init__(self):
        self.strings = {}
        self.sets = {}
        self.lists = {}
        self.claims = {}
        self.expirations = {}
        self.published = []

    def eval(self, script, numkeys, *args):
        keys = args[:numkeys]
        argv = args[numkeys:]
        if script == tasks.SCAN_EVENT_LUA:
            return self._scan_event(keys, argv)
        if script == tasks.CLAIM_FILE_LUA:
            return self._claim(keys, argv)
        if script == tasks.RELEASE_CLAIM_LUA:
            return self._release_claim(keys, argv)
        if script == tasks.FINALIZE_FILE_LUA:
            return self._finalize(keys, argv)
        if script == tasks.TOKEN_EXPIRED_LUA:
            return self._token_expired(keys, argv)
        if script == tasks.FAIL_SCAN_LUA:
            return self._fail_scan(keys, argv)
        raise AssertionError("unexpected Lua script")

    def pttl(self, key):
        return self.expirations.get(key, -2)

    def _publish(self, sequence_key, events_key, channel, raw_event, ttl):
        sequence = int(self.strings.get(sequence_key, 0)) + 1
        self.strings[sequence_key] = sequence
        event = json.loads(raw_event)
        event["sequence"] = sequence
        encoded = json.dumps(event, separators=(",", ":"))
        self.lists.setdefault(events_key, []).append(encoded)
        self.published.append((channel, encoded))
        self.expirations[sequence_key] = ttl
        self.expirations[events_key] = ttl
        return encoded

    def _scan_event(self, keys, argv):
        sequence_key, events_key, channel, counter_key, status_key, processed_key = keys
        raw_event, ttl = argv
        ttl = int(ttl)
        encoded = self._publish(sequence_key, events_key, channel, raw_event, ttl)
        for key in (counter_key, status_key, processed_key):
            if key in self.strings or key in self.sets:
                self.expirations[key] = ttl
        return encoded

    def _claim(self, keys, argv):
        processed_key, claim_key, counter_key, sequence_key, events_key, status_key = keys
        file_id, token, claim_ttl, scan_ttl = argv
        if self.strings.get(status_key) in {"completed", "token_expired", "failed"}:
            return 2
        if counter_key not in self.strings:
            return -2
        if int(self.strings[counter_key]) <= 0:
            return 0
        if file_id in self.sets.get(processed_key, set()):
            return 0
        if claim_key in self.claims:
            return -1
        self.claims[claim_key] = token
        self.expirations[claim_key] = int(claim_ttl) * 1000
        for key in (processed_key, counter_key, sequence_key, events_key, status_key):
            if key in self.strings or key in self.sets or key in self.lists:
                self.expirations[key] = int(scan_ttl)
        return 1

    def _release_claim(self, keys, argv):
        claim_key = keys[0]
        if self.claims.get(claim_key) != argv[0]:
            return 0
        del self.claims[claim_key]
        return 1

    def _finalize(self, keys, argv):
        counter_key, status_key, processed_key, sequence_key, events_key, channel = keys
        file_id, raw_event, ttl, scan_id = argv
        ttl = int(ttl)
        if counter_key not in self.strings:
            return ["missing_counter", ""]
        current = int(self.strings[counter_key])
        if current <= 0:
            return ["exhausted_counter", str(current)]
        processed = self.sets.setdefault(processed_key, set())
        if file_id in processed:
            return ["duplicate", str(current)]

        status = self.strings.get(status_key)
        processed.add(file_id)
        remaining = current - 1
        self.strings[counter_key] = remaining
        if status not in {"completed", "token_expired", "failed"} and raw_event:
            self._publish(sequence_key, events_key, channel, raw_event, ttl)
        if remaining == 0 and status is None:
            self.strings[status_key] = "completed"
            status = "completed"
            completed = json.dumps({"type": "completed", "scan_id": scan_id})
            self._publish(sequence_key, events_key, channel, completed, ttl)
        for key in (counter_key, status_key, processed_key, sequence_key, events_key):
            if key in self.strings or key in self.sets or key in self.lists:
                self.expirations[key] = ttl
        return [status or "running", str(remaining)]

    def _token_expired(self, keys, argv):
        counter_key, status_key, processed_key, sequence_key, events_key, channel = keys
        file_id, raw_event, ttl = argv
        ttl = int(ttl)
        if counter_key not in self.strings:
            return ["missing_counter", ""]
        current = int(self.strings[counter_key])
        if current <= 0:
            return ["exhausted_counter", str(current)]
        processed = self.sets.setdefault(processed_key, set())
        if file_id in processed:
            return ["duplicate", str(current)]

        first_expiration = status_key not in self.strings
        if first_expiration:
            self.strings[status_key] = "token_expired"
            self._publish(sequence_key, events_key, channel, raw_event, ttl)
        processed.add(file_id)
        self.strings[counter_key] = current - 1
        for key in (counter_key, status_key, processed_key, sequence_key, events_key):
            if key in self.strings or key in self.sets or key in self.lists:
                self.expirations[key] = ttl
        outcome = "token_expired" if first_expiration else "terminal_exists"
        return [outcome, str(current - 1)]

    def _fail_scan(self, keys, argv):
        status_key, sequence_key, events_key, channel = keys
        raw_event, ttl = argv
        ttl = int(ttl)
        if status_key in self.strings:
            return self.strings[status_key]
        self.strings[status_key] = "failed"
        self.expirations[status_key] = ttl
        self._publish(sequence_key, events_key, channel, raw_event, ttl)
        return "failed"


class FakePubSub:
    def __init__(self, messages):
        self.messages = messages
        self.subscribed = []
        self.unsubscribed = []
        self.subscription_acknowledged = False

    async def subscribe(self, channel):
        self.subscribed.append(channel)

    async def get_message(self, *, ignore_subscribe_messages, timeout):
        assert ignore_subscribe_messages is False
        assert timeout == 5.0
        self.subscription_acknowledged = True
        return {"type": "subscribe", "channel": self.subscribed[-1]}

    async def unsubscribe(self, channel):
        self.unsubscribed.append(channel)

    async def listen(self):
        for message in self.messages:
            yield message
        raise WebSocketDisconnect()


class FakeAsyncRedis:
    def __init__(self, *, events=(), messages=(), values=None):
        self.events = list(events)
        self.values = values or {}
        self._pubsub = FakePubSub(messages)
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def lrange(self, key, start, end):
        assert self._pubsub.subscription_acknowledged is True
        return self.events

    async def get(self, key):
        return self.values.get(key)

    async def mget(self, *keys):
        return [self.values.get(key) for key in keys]

    async def aclose(self):
        self.closed = True


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message):
        self.messages.append(message)


def encoded_event(sequence, event_type):
    return json.dumps({"type": event_type, "scan_id": "scan-a", "sequence": sequence})


def unauthorized_download(*args, **kwargs):
    request = tasks.httpx.Request("GET", "https://drive.example/file")
    response = tasks.httpx.Response(401, request=request)
    raise tasks.httpx.HTTPStatusError("unauthorized", request=request, response=response)


def test_websocket_replays_persisted_events_then_deduplicates_live_delivery(monkeypatch):
    first = encoded_event(1, "started")
    second = encoded_event(2, "progress")
    third = encoded_event(3, "match")
    redis_client = FakeAsyncRedis(
        events=[first, second],
        messages=[
            {"type": "message", "data": second},
            {"type": "message", "data": third},
        ],
    )
    monkeypatch.setattr(endpoints.redis, "from_url", lambda *args, **kwargs: redis_client)
    websocket = FakeWebSocket()

    asyncio.run(endpoints.websocket_endpoint(websocket, "scan-a"))

    assert websocket.accepted is True
    assert websocket.messages == [first, second, third]
    assert redis_client._pubsub.subscribed == ["scan_updates:scan-a"]
    assert redis_client._pubsub.unsubscribed == ["scan_updates:scan-a"]
    assert redis_client.closed is True


def test_websocket_can_resume_after_last_observed_sequence(monkeypatch):
    first = encoded_event(1, "started")
    second = encoded_event(2, "progress")
    third = encoded_event(3, "match")
    redis_client = FakeAsyncRedis(events=[first, second, third])
    monkeypatch.setattr(endpoints.redis, "from_url", lambda *args, **kwargs: redis_client)
    websocket = FakeWebSocket()

    asyncio.run(endpoints.websocket_endpoint(websocket, "scan-a", after_sequence=2))

    assert websocket.messages == [third]


def test_multiple_unauthorized_files_publish_one_terminal_event(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 2
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    tasks.expire_token_and_finalize("scan-a", "file-a")
    tasks.expire_token_and_finalize("scan-a", "file-b")

    events = [json.loads(item) for item in redis_client.lists["scan_events:scan-a"]]
    assert [event["type"] for event in events] == ["token_expired"]
    assert redis_client.strings["scan_status:scan-a"] == "token_expired"
    assert redis_client.strings["scan_remaining:scan-a"] == 0


def test_token_expiration_in_one_scan_does_not_affect_another(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 1
    redis_client.strings["scan_remaining:scan-b"] = 1
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    tasks.expire_token_and_finalize("scan-a", "file-a")
    tasks.finalize_file("scan-b", "file-b", {"type": "progress", "file_id": "file-b"})

    assert redis_client.strings["scan_status:scan-a"] == "token_expired"
    assert redis_client.strings["scan_status:scan-b"] == "completed"
    assert [channel for channel, _ in redis_client.published] == [
        "scan_updates:scan-a",
        "scan_updates:scan-b",
        "scan_updates:scan-b",
    ]


def test_in_flight_worker_cannot_publish_after_token_expired(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 2
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)
    tasks.expire_token_and_finalize("scan-a", "file-a")

    tasks.finalize_file(
        "scan-a",
        "file-b",
        {"type": "match", "file_id": "file-b", "status": "match"},
    )

    events = [json.loads(item) for item in redis_client.lists["scan_events:scan-a"]]
    assert [event["type"] for event in events] == ["token_expired"]
    assert redis_client.strings["scan_remaining:scan-a"] == 0


def test_redelivery_waits_for_claim_expiry_then_processes(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 1
    claim_key = "scan_claim:scan-a:file-a"
    redis_client.claims[claim_key] = "crashed-worker"
    redis_client.expirations[claim_key] = 37_001
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)
    monkeypatch.setattr(tasks, "download_file", unauthorized_download)
    retry_options = {}

    def retry(*args, **kwargs):
        retry_options.update(kwargs)
        raise tasks.Retry()

    monkeypatch.setattr(tasks.process_image, "retry", retry)

    try:
        tasks.process_image.run(
            file_id="file-a",
            file_name="a.jpg",
            access_token="expired",
            target_encoding_list=[],
            scan_id="scan-a",
        )
    except tasks.Retry:
        pass
    else:
        raise AssertionError("redelivery must retry while another claim is alive")

    assert retry_options["countdown"] == 38
    assert retry_options["kwargs"]["coordination_attempt"] == 1
    assert "file-a" not in redis_client.sets.get("scan_processed:scan-a", set())
    del redis_client.claims[claim_key]

    tasks.process_image.run(
        file_id="file-a",
        file_name="a.jpg",
        access_token="expired",
        target_encoding_list=[],
        scan_id="scan-a",
    )

    assert "file-a" in redis_client.sets["scan_processed:scan-a"]
    assert redis_client.strings["scan_status:scan-a"] == "token_expired"


def test_transport_retry_releases_claim_without_accounting(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 1
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    def unavailable_download(*args, **kwargs):
        request = tasks.httpx.Request("GET", "https://drive.example/file")
        raise tasks.httpx.ConnectError("unavailable", request=request)

    retry_options = {}

    def retry(*args, **kwargs):
        retry_options.update(kwargs)
        raise tasks.Retry()

    monkeypatch.setattr(tasks, "download_file", unavailable_download)
    monkeypatch.setattr(tasks.process_image, "retry", retry)

    try:
        tasks.process_image.run(
            file_id="file-a",
            file_name="a.jpg",
            access_token="token",
            target_encoding_list=[],
            scan_id="scan-a",
        )
    except tasks.Retry:
        pass
    else:
        raise AssertionError("transport failure should schedule a Celery retry")

    assert redis_client.strings["scan_remaining:scan-a"] == 1
    assert "file-a" not in redis_client.sets.get("scan_processed:scan-a", set())
    assert "scan_claim:scan-a:file-a" not in redis_client.claims
    assert redis_client.published == []
    assert retry_options["kwargs"]["transport_attempt"] == 1


def test_missing_counter_retries_instead_of_acknowledging_or_completing(monkeypatch):
    redis_client = FakeScanRedis()
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)
    retry_options = {}

    def unexpected_download(*args, **kwargs):
        raise AssertionError("missing counter must be handled before Drive access")

    def retry(*args, **kwargs):
        retry_options.update(kwargs)
        raise tasks.Retry()

    monkeypatch.setattr(tasks, "download_file", unexpected_download)
    monkeypatch.setattr(tasks.process_image, "retry", retry)

    try:
        tasks.process_image.run(
            file_id="file-a",
            file_name="a.jpg",
            access_token="token",
            target_encoding_list=[],
            scan_id="scan-a",
        )
    except tasks.Retry:
        pass
    else:
        raise AssertionError("missing counter must schedule a controlled retry")

    assert retry_options["countdown"] == 1
    assert isinstance(retry_options["exc"], RuntimeError)
    assert retry_options["kwargs"]["coordination_attempt"] == 1
    assert "scan_status:scan-a" not in redis_client.strings
    assert redis_client.published == []


def test_coordination_retry_does_not_consume_three_transport_retries(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 1
    claim_key = "scan_claim:scan-a:file-a"
    redis_client.claims[claim_key] = "other-worker"
    redis_client.expirations[claim_key] = 1_001
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)
    scheduled_retries = []

    def retry(*args, **kwargs):
        scheduled_retries.append(kwargs)
        raise tasks.Retry()

    monkeypatch.setattr(tasks.process_image, "retry", retry)

    try:
        tasks.process_image.run(
            file_id="file-a",
            file_name="a.jpg",
            access_token="token",
            target_encoding_list=[],
            scan_id="scan-a",
        )
    except tasks.Retry:
        pass
    del redis_client.claims[claim_key]

    download_attempts = 0

    def unavailable_download(*args, **kwargs):
        nonlocal download_attempts
        download_attempts += 1
        request = tasks.httpx.Request("GET", "https://drive.example/file")
        raise tasks.httpx.ConnectError("unavailable", request=request)

    monkeypatch.setattr(tasks, "download_file", unavailable_download)
    for transport_attempt in range(tasks.MAX_RETRIES):
        try:
            tasks.process_image.run(
                file_id="file-a",
                file_name="a.jpg",
                access_token="token",
                target_encoding_list=[],
                scan_id="scan-a",
                transport_attempt=transport_attempt,
                coordination_attempt=1,
            )
        except tasks.Retry:
            pass
        else:
            raise AssertionError("each allowed transport retry must be scheduled")

    tasks.process_image.run(
        file_id="file-a",
        file_name="a.jpg",
        access_token="token",
        target_encoding_list=[],
        scan_id="scan-a",
        transport_attempt=tasks.MAX_RETRIES,
        coordination_attempt=1,
    )

    assert scheduled_retries[0]["kwargs"]["coordination_attempt"] == 1
    assert [item["kwargs"]["transport_attempt"] for item in scheduled_retries[1:]] == [1, 2, 3]
    assert [item["kwargs"]["coordination_attempt"] for item in scheduled_retries[1:]] == [1, 1, 1]
    assert download_attempts == 4
    events = [json.loads(item) for item in redis_client.lists["scan_events:scan-a"]]
    assert [event["type"] for event in events] == ["error", "completed"]


def test_missing_counter_exhaustion_fails_scan_once(monkeypatch):
    redis_client = FakeScanRedis()
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    def unexpected_download(*args, **kwargs):
        raise AssertionError("expired scan state must fail before Drive access")

    monkeypatch.setattr(tasks, "download_file", unexpected_download)

    for file_id in ("file-a", "file-b"):
        tasks.process_image.run(
            file_id=file_id,
            file_name=f"{file_id}.jpg",
            access_token="token",
            target_encoding_list=[],
            scan_id="scan-a",
            coordination_attempt=tasks.MAX_COORDINATION_RETRIES,
        )

    events = [json.loads(item) for item in redis_client.lists["scan_events:scan-a"]]
    assert redis_client.strings["scan_status:scan-a"] == "failed"
    assert [event["type"] for event in events] == ["error"]
    assert events[0]["status"] == "failed"
    assert events[0]["sequence"] == 1


def test_missing_counter_never_creates_completion(monkeypatch):
    redis_client = FakeScanRedis()
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    result = tasks.finalize_file(
        "scan-a",
        "file-a",
        {"type": "progress", "file_id": "file-a", "status": "no_match"},
    )

    assert result == ["missing_counter", ""]
    assert "scan_status:scan-a" not in redis_client.strings
    assert redis_client.published == []


def test_finalization_is_idempotent_and_has_one_completed_terminal(monkeypatch):
    redis_client = FakeScanRedis()
    redis_client.strings["scan_remaining:scan-a"] = 2
    monkeypatch.setattr(tasks, "redis_text_client", redis_client)

    tasks.finalize_file("scan-a", "file-a", {"type": "progress", "file_id": "file-a"})
    tasks.finalize_file("scan-a", "file-b", {"type": "match", "file_id": "file-b"})
    tasks.finalize_file("scan-a", "file-b", {"type": "match", "file_id": "file-b"})

    events = [json.loads(item) for item in redis_client.lists["scan_events:scan-a"]]
    assert [event["type"] for event in events] == ["progress", "match", "completed"]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert redis_client.strings["scan_remaining:scan-a"] == 0
    assert redis_client.strings["scan_status:scan-a"] == "completed"
    for key in (
        "scan_remaining:scan-a",
        "scan_status:scan-a",
        "scan_processed:scan-a",
        "scan_sequence:scan-a",
        "scan_events:scan-a",
    ):
        assert redis_client.expirations[key] == tasks.SCAN_STATUS_TTL


def test_polling_exposes_running_and_all_terminal_or_unknown_states(monkeypatch):
    cases = [
        (
            {"scan_remaining:scan-a": "2", "scan_sequence:scan-a": "4"},
            {"scan_id": "scan-a", "status": "running", "remaining": 2, "last_sequence": 4},
        ),
        (
            {"scan_status:scan-a": "completed", "scan_sequence:scan-a": "7"},
            {"scan_id": "scan-a", "status": "completed", "remaining": 0, "last_sequence": 7},
        ),
        (
            {"scan_status:scan-a": "token_expired", "scan_sequence:scan-a": "3"},
            {"scan_id": "scan-a", "status": "token_expired", "remaining": 0, "last_sequence": 3},
        ),
        (
            {"scan_status:scan-a": "failed", "scan_sequence:scan-a": "1"},
            {"scan_id": "scan-a", "status": "failed", "remaining": 0, "last_sequence": 1},
        ),
        ({}, {"scan_id": "scan-a", "status": "unknown", "last_sequence": 0}),
    ]

    for values, expected in cases:
        redis_client = FakeAsyncRedis(values=values)
        monkeypatch.setattr(endpoints.redis, "from_url", lambda *args, **kwargs: redis_client)
        assert asyncio.run(endpoints.get_scan_status("scan-a")) == expected
        assert redis_client.closed is True
