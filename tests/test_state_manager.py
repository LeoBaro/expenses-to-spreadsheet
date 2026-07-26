"""State Manager tests (TR-7)."""

from __future__ import annotations

from expenses.state.manager import StateManager


def test_unprocessed_by_default(tmp_path):
    state = StateManager(tmp_path / "state.log")
    assert state.is_processed("tx-1") is False


def test_mark_then_is_processed(tmp_path):
    state = StateManager(tmp_path / "state.log")
    state.mark_processed("tx-1")
    assert state.is_processed("tx-1") is True
    assert state.is_processed("tx-2") is False


def test_persists_across_instances(tmp_path):
    path = tmp_path / "state.log"
    first = StateManager(path)
    first.mark_processed("tx-1")
    first.mark_processed("tx-2")

    second = StateManager(path)
    second.load()
    assert second.is_processed("tx-1")
    assert second.is_processed("tx-2")


def test_mark_is_idempotent_no_duplicate_lines(tmp_path):
    path = tmp_path / "state.log"
    state = StateManager(path)
    state.mark_processed("tx-1")
    state.mark_processed("tx-1")
    assert path.read_text(encoding="utf-8").splitlines() == ["tx-1"]


def test_appends_immediately(tmp_path):
    path = tmp_path / "state.log"
    state = StateManager(path)
    state.mark_processed("tx-1")
    # Written to disk before the call returns (FR-13 "immediately persisted").
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "tx-1\n"


def test_load_missing_file_is_noop(tmp_path):
    state = StateManager(tmp_path / "nope.log")
    state.load()
    assert state.is_processed("x") is False


def test_load_tolerates_blank_and_partial_lines(tmp_path):
    path = tmp_path / "state.log"
    # A crash mid-append could leave a trailing line without a newline.
    path.write_text("tx-1\n\ntx-2\npartial", encoding="utf-8")
    state = StateManager(path)
    state.load()
    assert state.is_processed("tx-1")
    assert state.is_processed("tx-2")
    assert state.is_processed("partial")  # harmless bogus id, no crash


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "state.log"
    StateManager(path).mark_processed("tx-1")
    assert path.exists()
