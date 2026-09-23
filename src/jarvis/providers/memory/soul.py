"""Adaptateur Soul pour la mémoire canonique de Holmes.

Le transport MCP est injecté : Holmes connaît l'intention ``write_note``,
mais reste indépendant de la manière dont Codex, Claude ou un serveur local
établit la session MCP.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from jarvis.kernel.contracts import CanonicalTask
from jarvis.kernel.holmes_memory import CanonicalMemoryEvent


class SoulToolClient(Protocol):
    """Sous-ensemble du client MCP requis par SoulMemoryStore."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...  # noqa: ANN401


class SoulMCPError(RuntimeError):
    """Erreur de protocole ou de transport provenant du serveur MCP Soul."""


class SoulMCPClient:
    """Client minimal du transport HTTP MCP utilisé par Soul/Basic Memory.

    Une session MCP est créée paresseusement au premier appel. Le client ne
    connaît aucune opération métier Holmes ; il expose seulement ``call_tool``
    à l'adaptateur ``SoulMemoryStore``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint.strip():
            raise ValueError("L'URL MCP Soul ne peut pas être vide")
        self._endpoint = endpoint.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = http_client is None
        self._session_id: str | None = None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:  # noqa: ANN401
        await self._initialize()
        result = await self._request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if "error" in result:
            raise SoulMCPError(str(result["error"]))
        payload = result.get("result")
        if not isinstance(payload, Mapping):
            raise SoulMCPError("Réponse MCP Soul invalide")
        if payload.get("isError"):
            raise SoulMCPError(str(payload.get("content", "Écriture Soul refusée")))
        structured = payload.get("structuredContent")
        if isinstance(structured, Mapping) and "result" in structured:
            return structured["result"]
        return payload

    async def _initialize(self) -> None:
        if self._session_id is not None:
            return
        result, session_id = await self._request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "holmes-os", "version": "0.1"},
                },
            },
            include_session=False,
        )
        if "error" in result or not isinstance(result.get("result"), Mapping):
            raise SoulMCPError(f"Initialisation MCP Soul refusée : {result}")
        if not session_id:
            raise SoulMCPError("Soul n'a pas retourné d'identifiant de session MCP")
        self._session_id = session_id

    async def _request(
        self,
        payload: dict[str, Any],
        *,
        include_session: bool = True,
    ) -> tuple[dict[str, Any], str | None] | dict[str, Any]:
        headers = {"Accept": "application/json, text/event-stream"}
        if include_session and self._session_id is not None:
            headers["mcp-session-id"] = self._session_id
        response = await self._client.post(self._endpoint, headers=headers, json=payload)
        response.raise_for_status()
        parsed = self._parse_message(response.text)
        if include_session:
            return parsed
        return parsed, response.headers.get("mcp-session-id")

    @staticmethod
    def _parse_message(body: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for line in body.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                parsed = json.loads(line.removeprefix("data: "))
            except json.JSONDecodeError as exc:
                raise SoulMCPError("Réponse MCP Soul illisible") from exc
            if not isinstance(parsed, dict):
                raise SoulMCPError("Réponse MCP Soul invalide")
            messages.append(parsed)

        if not messages:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                raise SoulMCPError("Réponse MCP Soul illisible") from exc
            if not isinstance(parsed, dict):
                raise SoulMCPError("Réponse MCP Soul invalide")
            return parsed

        # Certains appels Soul diffusent une notification de progression avant
        # la réponse JSON-RPC. Nous devons conserver la réponse, pas l'event.
        for message in reversed(messages):
            if "result" in message or "error" in message:
                return message
        return messages[-1]


class SoulMemoryStore:
    """Écrit chaque événement canonique dans Soul avec une provenance complète."""

    def __init__(
        self,
        client: SoulToolClient,
        *,
        project: str | None = None,
        directory: str = "holmes/events",
    ) -> None:
        self._client = client
        self._project = project
        self._directory = directory.strip("/")

    async def append_event(self, event: CanonicalMemoryEvent) -> str:
        """Crée une note Soul immuable pour un fait déjà filtré par Holmes."""
        metadata: dict[str, Any] = {
            "event_id": event.event_id,
            "source": event.source.value,
            "occurred_at": event.occurred_at.isoformat(),
            "source_metadata": dict(event.metadata),
        }
        arguments: dict[str, Any] = {
            "title": f"Holmes memory {event.event_id}",
            "content": self._render(event),
            "directory": self._directory,
            "tags": f"holmes,memory,{event.source.value}",
            "note_type": "event",
            "metadata": metadata,
            # Un event_id UUID garantit l'unicité. On refuse donc de modifier
            # silencieusement une entrée existante si une collision survient.
            "overwrite": False,
            "output_format": "json",
        }
        if self._project is not None:
            arguments["project"] = self._project

        result = await self._client.call_tool("write_note", arguments)
        return self._reference(event, result)

    @staticmethod
    def _render(event: CanonicalMemoryEvent) -> str:
        return (
            "# Événement mémoire Holmes\n\n"
            f"Source : `{event.source.value}`\n"
            f"Date : `{event.occurred_at.isoformat()}`\n\n"
            f"{event.content.strip()}\n"
        )

    @staticmethod
    def _reference(event: CanonicalMemoryEvent, result: Any) -> str:  # noqa: ANN401
        if isinstance(result, Mapping):
            for key in ("permalink", "path", "id", "url"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
        return f"soul://holmes/events/{event.event_id}"


class SoulTaskStore:
    """Liste de tâches Holmes persistée comme note canonique unique dans Soul."""

    _IDENTIFIER = "holmes/tasks"
    _JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

    def __init__(self, client: SoulToolClient, *, project: str | None = None) -> None:
        self._client = client
        self._project = project
        self._lock = asyncio.Lock()

    async def list_tasks(self) -> list[CanonicalTask]:
        async with self._lock:
            return await self._read_unlocked()

    async def create_task(self, text: str) -> CanonicalTask:
        clean = " ".join(text.split()).strip()
        if not clean:
            raise ValueError("Le texte de la tâche ne peut pas être vide")
        async with self._lock:
            tasks = await self._read_unlocked()
            task = CanonicalTask(id=f"task_{uuid.uuid4().hex[:10]}", text=clean)
            tasks.append(task)
            await self._write_unlocked(tasks)
            return task

    async def update_task(
        self,
        task_id: str,
        *,
        text: str | None = None,
        done: bool | None = None,
    ) -> CanonicalTask:
        async with self._lock:
            tasks = await self._read_unlocked()
            for index, task in enumerate(tasks):
                if task.id != task_id:
                    continue
                clean = " ".join(text.split()).strip() if text is not None else task.text
                if not clean:
                    raise ValueError("Le texte de la tâche ne peut pas être vide")
                updated = CanonicalTask(
                    id=task.id,
                    text=clean,
                    done=task.done if done is None else done,
                )
                tasks[index] = updated
                await self._write_unlocked(tasks)
                return updated
        raise KeyError(task_id)

    async def delete_task(self, task_id: str) -> bool:
        async with self._lock:
            tasks = await self._read_unlocked()
            kept = [task for task in tasks if task.id != task_id]
            if len(kept) == len(tasks):
                return False
            await self._write_unlocked(kept)
            return True

    async def _read_unlocked(self) -> list[CanonicalTask]:
        arguments: dict[str, Any] = {
            "identifier": self._IDENTIFIER,
            "output_format": "text",
        }
        if self._project is not None:
            arguments["project"] = self._project
        try:
            raw = await self._client.call_tool("read_note", arguments)
        except SoulMCPError:
            return []
        if not isinstance(raw, str):
            return []
        match = self._JSON_BLOCK.search(raw)
        if match is None:
            return []
        try:
            rows = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise SoulMCPError("La note de tâches Soul contient un JSON invalide") from exc
        if not isinstance(rows, list):
            raise SoulMCPError("La note de tâches Soul ne contient pas une liste")
        return [
            CanonicalTask(id=str(row["id"]), text=str(row["text"]), done=bool(row.get("done")))
            for row in rows
            if isinstance(row, Mapping) and row.get("id") and row.get("text")
        ]

    async def _write_unlocked(self, tasks: list[CanonicalTask]) -> None:
        payload = [{"id": task.id, "text": task.text, "done": task.done} for task in tasks]
        checklist = "\n".join(
            f"- [{'x' if task.done else ' '}] {task.text} (`{task.id}`)" for task in tasks
        ) or "_Aucune tâche._"
        content = (
            "# Tâches Holmes\n\n"
            "Cette note est la liste canonique utilisée par Holmes OS et la voix.\n\n"
            f"{checklist}\n\n"
            "```json\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "```\n"
        )
        arguments: dict[str, Any] = {
            "title": "Tasks",
            "content": content,
            "directory": "holmes",
            "tags": "holmes,tasks",
            "note_type": "entity",
            "overwrite": True,
            "output_format": "json",
        }
        if self._project is not None:
            arguments["project"] = self._project
        await self._client.call_tool("write_note", arguments)


class SoulRecall:
    """Recherche Soul injectée dans le contexte de chaque tour Holmes."""

    always_recall = True
    _CT_INVENTORY_ENTRY = re.compile(r"^- \[[^\]]+\] \*\*CT \d+", re.MULTILINE)

    def __init__(
        self,
        client: SoulToolClient,
        *,
        project: str | None = None,
        max_chars: int = 6_000,
    ) -> None:
        self._client = client
        self._project = project
        self._max_chars = max_chars

    async def recall(self, query: str, k: int = 5) -> str | None:
        query = self._normalize_query(query)
        if not query:
            return None
        result = await self._search(query, k=k)
        if not isinstance(result, str) or not result.strip():
            return None

        reference_note = await self._load_referenced_note(query)
        if reference_note:
            facts = self._derive_facts(reference_note)
            facts_section = f"## Faits extraits de Soul\n\n{facts}\n\n" if facts else ""
            result = (
                f"{facts_section}## Note de référence Soul\n\n{reference_note}"
                f"\n\n## Résultats Soul\n\n{result.strip()}"
            )
        return result.strip()[: self._max_chars]

    @staticmethod
    def direct_answer(query: str, recall_summary: str) -> str | None:
        """Répond aux totaux Soul explicitement dérivés, sans inférence LLM."""
        normalized = SoulRecall._normalize_query(query)
        asks_for_count = re.search(r"\b(combien|nombre|total)\b", normalized, re.IGNORECASE)
        asks_for_ct = re.search(r"\b(ct|conteneurs?)\b", normalized, re.IGNORECASE)
        total = re.search(r"\*\*(\d+) conteneurs CT\*\*", recall_summary)
        if not (asks_for_count and asks_for_ct and total):
            return None

        title = re.search(r"^title:\s*(.+)$", recall_summary, re.MULTILINE)
        scope = title.group(1).strip() if title else "l'inventaire Soul"
        return f"Il y a {total.group(1)} conteneurs CT dans {scope}."

    @staticmethod
    def _normalize_query(query: str) -> str:
        """Retire les marqueurs de transport ajoutés par l'interface vocale."""
        return re.sub(r"\s*\[voix\]\s*$", "", query, flags=re.IGNORECASE).strip()

    async def _search(self, query: str, *, k: int) -> Any:  # noqa: ANN401
        arguments: dict[str, Any] = {
            "query": query,
            "page_size": min(max(k, 1), 10),
            "output_format": "text",
        }
        if self._project is not None:
            arguments["project"] = self._project
        else:
            arguments["search_all_projects"] = True
        return await self._client.call_tool("search_notes", arguments)

    async def _load_referenced_note(self, query: str) -> str | None:
        """Hydrate la note nommée dans une question, si Soul la retrouve."""
        terms = self._meaningful_terms(query)
        focus = terms[-1] if terms else None
        if focus is None or focus == query.strip().casefold():
            return None

        reference_query = " ".join(reversed(terms[-2:]))
        result = await self._search(reference_query, k=5)
        if not isinstance(result, str):
            return None
        permalink = self._matching_permalink(result, focus)
        if permalink is None:
            return None

        note = await self._client.call_tool(
            "read_note", {"identifier": permalink, "output_format": "text"}
        )
        return note.strip() if isinstance(note, str) and note.strip() else None

    @staticmethod
    def _focus_term(query: str) -> str | None:
        terms = SoulRecall._meaningful_terms(query)
        return terms[-1] if terms else None

    @staticmethod
    def _meaningful_terms(query: str) -> list[str]:
        ignored = {
            "a",
            "au",
            "aux",
            "ce",
            "ces",
            "combien",
            "dans",
            "de",
            "des",
            "du",
            "en",
            "est",
            "il",
            "je",
            "la",
            "le",
            "les",
            "ma",
            "maison",
            "me",
            "mon",
            "pour",
            "que",
            "quel",
            "quelle",
            "quels",
            "sur",
            "tu",
            "un",
            "une",
            "y",
        }
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        return [
            term
            for term in terms
            if (len(term) > 2 or term.isupper()) and term.casefold() not in ignored
        ]

    @staticmethod
    def _matching_permalink(search_result: str, focus: str) -> str | None:
        for permalink in re.findall(r"^- permalink: ([^\n]+)$", search_result, flags=re.MULTILINE):
            candidate = permalink.strip()
            if candidate.casefold().rsplit("/", 1)[-1] == focus.casefold():
                return candidate
        return None

    @classmethod
    def _derive_facts(cls, note: str) -> str | None:
        """Expose les totaux d'inventaire sans déléguer le comptage au LLM."""
        ct_count = len(cls._CT_INVENTORY_ENTRY.findall(note))
        if not ct_count:
            return None
        return (
            f"- Total : **{ct_count} conteneurs CT** inventoriés dans cette note. "
            "Un même numéro de CT peut exister sur plusieurs hôtes ; ce total compte "
            "les entrées de conteneurs, pas les numéros uniques."
        )
