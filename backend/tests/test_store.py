import json
import threading

import pytest
from contracts import VersionRef, content_sha256

from app.utils import store


def test_write_once_creates_and_refuses_overwrite(data_dir):
    store.write_once("inspections/ins_1/inspection.json", {"status": "complete"})
    assert store.read_json("inspections/ins_1/inspection.json") == {"status": "complete"}
    with pytest.raises(store.AlreadyExistsError):
        store.write_once("inspections/ins_1/inspection.json", {"status": "partial"})
    assert store.read_json("inspections/ins_1/inspection.json") == {"status": "complete"}
    # no temp files left behind
    assert store.list_dir("inspections/ins_1") == ["inspection.json"]


def test_write_once_bytes(data_dir):
    store.write_once("inspections/ins_1/screenshot.png", b"\x89PNG")
    assert store.read_bytes("inspections/ins_1/screenshot.png") == b"\x89PNG"


def test_paths_cannot_escape_data_root():
    with pytest.raises(ValueError):
        store.write_once("../outside.json", {})
    with pytest.raises(ValueError):
        store.read_json("/etc/passwd")


def test_read_missing_raises_not_found():
    with pytest.raises(store.NotFoundError):
        store.read_json("sessions/none/session.json")


def test_update_json_creates_and_increments_rev():
    path = "sessions/ses_1/session.json"
    first = store.update_json(path, lambda s: {**s, "goals": ["a"]}, expected_rev=0)
    assert first["rev"] == 1
    second = store.update_json(path, lambda s: {**s, "goals": s["goals"] + ["b"]}, expected_rev=1)
    assert second == {"goals": ["a", "b"], "rev": 2}
    assert store.read_json(path) == second


def test_update_json_stale_rev_conflicts_and_writes_nothing():
    path = "sessions/ses_1/session.json"
    store.update_json(path, lambda s: {"goal": "a"}, expected_rev=0)
    store.update_json(path, lambda s: {"goal": "b"}, expected_rev=1)
    with pytest.raises(store.ConflictError) as info:
        store.update_json(path, lambda s: {"goal": "stale"}, expected_rev=1)
    assert info.value.current_rev == 2
    assert store.read_json(path) == {"goal": "b", "rev": 2}


def test_update_json_without_expected_rev_always_applies():
    path = "sessions/ses_1/session.json"
    store.update_json(path, lambda s: {"n": 1}, expected_rev=None)
    assert store.update_json(path, lambda s: {"n": s["n"] + 1}, expected_rev=None) == {"n": 2, "rev": 2}


def test_append_jsonl_appends_lines(data_dir):
    path = "usage/model_calls.jsonl"
    assert store.read_jsonl(path) == []
    store.append_jsonl(path, {"call_id": "call_1"})
    store.append_jsonl(path, {"call_id": "call_2", "text": "line\nbreak"})
    assert store.read_jsonl(path) == [{"call_id": "call_1"}, {"call_id": "call_2", "text": "line\nbreak"}]
    assert len((data_dir / path).read_text().splitlines()) == 2


def test_concurrent_append_jsonl_does_not_interleave(data_dir):
    path = "usage/model_calls.jsonl"
    big = "x" * 20_000  # large records make interleaving visible if locking were broken
    per_thread = 50

    def writer(name):
        for i in range(per_thread):
            store.append_jsonl(path, {"writer": name, "i": i, "pad": big})

    threads = [threading.Thread(target=writer, args=(name,)) for name in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = (data_dir / path).read_text().splitlines()
    assert len(lines) == 2 * per_thread
    records = [json.loads(line) for line in lines]  # every line is complete JSON
    for name in ("a", "b"):
        assert [r["i"] for r in records if r["writer"] == name] == list(range(per_thread))


def test_append_version_numbers_and_hash():
    content = {"cases": [{"tc_id": "tc_1", "title": "login"}]}
    v1 = store.append_version("test_plan", "tp_1", content, session_id="ses_1", created_by="tester")
    v2 = store.append_version(
        "test_plan",
        "tp_1",
        {"cases": []},
        session_id="ses_1",
        created_by="tester",
        derived_from=[VersionRef(kind="test_plan", id="tp_1", version=1)],
    )
    v3 = store.append_version("test_plan", "tp_1", content, session_id="ses_1", created_by="tester", restored_from=1)

    assert (v1.version, v2.version, v3.version) == (1, 2, 3)
    assert v1.content_sha256 == content_sha256(content) == v3.content_sha256
    assert v2.content_sha256 != v1.content_sha256
    assert store.list_versions("test_plan", "tp_1") == [1, 2, 3]
    assert store.read_version("test_plan", "tp_1") == v3
    assert store.read_version("test_plan", "tp_1", 2).derived_from[0].version == 1
    assert store.read_version("test_plan", "tp_1", 3).restored_from == 1


def test_append_version_hash_is_canonical():
    a = store.append_version("repair", "rep_1", {"b": 1, "a": 2}, session_id="s", created_by="x")
    b = store.append_version("repair", "rep_2", {"a": 2, "b": 1}, session_id="s", created_by="x")
    assert a.content_sha256 == b.content_sha256


def test_append_version_concurrent_writers_get_distinct_numbers():
    results = []

    def writer(i):
        env = store.append_version("test_code", "code_1", {"i": i}, session_id="s", created_by="x")
        results.append(env.version)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == list(range(1, 11))


def test_append_version_skips_existing_file(data_dir):
    # a v1 that appeared without going through the lock is never overwritten
    (data_dir / "artifacts/test_plan/tp_9").mkdir(parents=True)
    (data_dir / "artifacts/test_plan/tp_9/v1.json").write_text("{}")
    env = store.append_version("test_plan", "tp_9", {}, session_id="s", created_by="x")
    assert env.version == 2


def test_append_version_rejects_unknown_kind():
    with pytest.raises(ValueError):
        store.append_version("session", "ses_1", {}, session_id="s", created_by="x")
