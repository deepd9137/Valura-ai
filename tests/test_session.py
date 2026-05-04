"""
Unit tests for SessionStore.
No LLM calls, no mocks.
"""
from src.session import SessionStore


def test_get_unknown_session_returns_empty():
    store = SessionStore()
    assert store.get("nonexistent") == []


def test_append_and_get_single_turn():
    store = SessionStore()
    store.append("s1", "hello")
    assert store.get("s1") == ["hello"]


def test_append_multiple_turns_ordered_oldest_first():
    store = SessionStore()
    store.append("s1", "first")
    store.append("s1", "second")
    store.append("s1", "third")
    turns = store.get("s1")
    assert turns == ["first", "second", "third"]


def test_session_store_caps_at_max_turns():
    store = SessionStore(max_turns=3)
    for i in range(6):
        store.append("s1", f"turn {i}")
    turns = store.get("s1")
    assert len(turns) == 3
    # oldest turns evicted; most recent kept
    assert turns == ["turn 3", "turn 4", "turn 5"]


def test_session_store_isolated_per_session_id():
    store = SessionStore()
    store.append("sess_a", "alpha")
    store.append("sess_b", "beta")
    assert store.get("sess_a") == ["alpha"]
    assert store.get("sess_b") == ["beta"]


def test_clear_removes_session():
    store = SessionStore()
    store.append("s1", "hello")
    store.clear("s1")
    assert store.get("s1") == []


def test_clear_nonexistent_session_does_not_raise():
    store = SessionStore()
    store.clear("ghost")  # should not raise


def test_get_returns_copy_not_reference():
    store = SessionStore()
    store.append("s1", "hello")
    turns = store.get("s1")
    turns.append("injected")
    # internal state should be unchanged
    assert store.get("s1") == ["hello"]


def test_default_max_turns_is_five():
    store = SessionStore(max_turns=5)
    for i in range(7):
        store.append("s1", str(i))
    assert len(store.get("s1")) == 5


def test_len_counts_sessions():
    store = SessionStore()
    assert len(store) == 0
    store.append("s1", "a")
    store.append("s2", "b")
    assert len(store) == 2
