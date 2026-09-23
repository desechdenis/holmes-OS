# Copyright (C) 2026 Barthélemy Houot
# This file is part of Jarvis OS, licensed under the GNU AGPL-3.0-or-later.
# See the LICENSE file or <https://www.gnu.org/licenses/agpl-3.0.html>.

from __future__ import annotations

from jarvis.engine.agent import _active_session_messages
from jarvis.engine.session import Session, SessionManager


def test_session_add_message() -> None:
    session = Session()
    session.add_message("user", "Bonjour")
    session.add_message("assistant", "Salut chef.")
    assert len(session.messages) == 2
    assert session.messages[0] == {"role": "user", "content": "Bonjour"}


def test_session_add_message_unless_last_avoids_transport_duplicate() -> None:
    persisted: list[tuple[str, str]] = []
    session = Session()
    session.set_persist(lambda role, content: persisted.append((role, content)))

    assert session.add_message_unless_last("assistant", "Tâche ajoutée") is True
    assert session.add_message_unless_last("assistant", "Tâche ajoutée") is False

    assert session.messages == [{"role": "assistant", "content": "Tâche ajoutée"}]
    assert persisted == [("assistant", "Tâche ajoutée")]


def test_session_manager_create() -> None:
    mgr = SessionManager()
    session = mgr.get_or_create()
    assert session is not None
    assert str(session.id) in mgr.list_ids()


def test_session_manager_get_existing() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create()
    s2 = mgr.get_or_create(str(s1.id))
    assert s1.id == s2.id


def test_session_manager_get_none() -> None:
    mgr = SessionManager()
    result = mgr.get("non-existent-id")
    assert result is None


def test_session_manager_unknown_id_creates_new() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create("unknown-uuid")
    s2 = mgr.get_or_create("unknown-uuid")
    # "unknown-uuid" n'est pas dans le registre, donc deux sessions distinctes
    # (get_or_create crée une nouvelle si l'id n'est pas connu)
    assert s1.id != s2.id


def test_active_llm_context_is_bounded_without_truncating_session() -> None:
    session = Session()
    for index in range(20):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"réponse {index}")

    active = _active_session_messages(session)

    assert len(session.messages) == 40
    assert len(active) <= 24
    assert active[0]["role"] == "user"
    assert active[-1]["content"] == "réponse 19"
