"""Outil vocal et conversationnel pour la liste canonique de tâches Soul."""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.contracts import CanonicalTaskStore


@dataclass(frozen=True)
class TaskCommandOutcome:
    """Résultat vérifiable d'une commande de tâche déterministe."""

    content: str
    succeeded: bool


def parse_task_command(text: str) -> tuple[str, str | None] | None:
    """Extrait les commandes usuelles sans laisser le LLM prétendre les avoir exécutées."""
    clean = re.sub(r"\s*\[voix\]\s*$", "", text, flags=re.IGNORECASE).strip()
    clean = clean.strip(' \t\r\n"“”«»')
    clean = re.sub(r"[.!?…]+\s*[" + re.escape('"“”«»') + r"]?\s*$", "", clean).strip()
    create_patterns = (
        r"\b(?:ajoute|ajouter|crée|créer|note)\s+(?:la\s+|une\s+)?t[aâ]che\s*:?[\s\"]*(.+?)\"?$",
        r"\b(?:ajoute|ajouter|crée|créer|note|mets|mettre)\s+"
        r"(?:à|a|dans|sur)\s+(?:ma|la|mes|les)?\s*"
        r"(?:liste(?:\s+(?:de\s+)?(?:t[aâ]ches|choses\s+à\s+faire))?|choses\s+à\s+faire)"
        r"\s*:?[\s\"]*(.+?)\"?$",
        r"\b(?:ajoute|ajouter|crée|créer|note|mets|mettre)\s+(.+?)\s+"
        r"(?:à|a|dans|sur)\s+(?:ma|la|mes|les)?\s*"
        r"(?:liste(?:\s+(?:de\s+)?(?:t[aâ]ches|choses\s+à\s+faire))?|choses\s+à\s+faire)$",
        # Forme vocale courte : « ajoute aller dormir » / « ajoute sortir les poubelles ».
        r"\b(?:ajoute|ajouter|crée|créer|note)\s+"
        r"((?:aller|acheter|appeler|classer|dormir|faire|nettoyer|penser|préparer|prendre|"
        r"ranger|réparer|sortir|vérifier)\b.+)$",
    )
    for pattern in create_patterns:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            value = re.sub(
                r"\s+(?:s['’]il\s+te\s+pla[iî]t|stp)\s*$",
                "",
                match.group(1),
                flags=re.IGNORECASE,
            ).strip(' ."“”«»')
            return "create", value

    complete = re.search(
        r"\b(?:marque|mets)\s+(?:la\s+)?t[aâ]che\s+(.+?)\s+"
        r"(?:comme\s+)?(?:faite|terminée|terminee)$",
        clean,
        re.IGNORECASE,
    )
    if complete:
        return "complete", complete.group(1).strip(" .\"")
    delete = re.search(
        r"\b(?:supprime|efface)\s+(?:la\s+)?t[aâ]che\s+(.+)$",
        clean,
        re.IGNORECASE,
    )
    if delete:
        return "delete", delete.group(1).strip(" .\"")
    if re.search(
        r"\b(?:quelles? sont|liste|lis|montre)(?:-moi)?\b.*\b"
        r"(?:t[aâ]ches|choses à faire)\b",
        clean,
        re.IGNORECASE,
    ):
        return "list", None
    return None


async def execute_task_command(task_tool: object | None, text: str) -> TaskCommandOutcome | None:
    """Exécute une commande reconnue et conserve le statut réel retourné par Soul."""
    command = parse_task_command(text)
    if command is None:
        return None
    if task_tool is None:
        return TaskCommandOutcome(
            "Le service de tâches Soul n'est pas disponible.",
            False,
        )

    action, value = command
    if action in ("create", "list"):
        result = await task_tool.execute(  # type: ignore[attr-defined]
            action=action, **({"text": value} if value else {})
        )
        return TaskCommandOutcome(result.content, not result.is_error)

    listed = await task_tool.execute(action="list")  # type: ignore[attr-defined]
    if listed.is_error:
        return TaskCommandOutcome(listed.content, False)
    target = (value or "").casefold()
    task_id = None
    for line in listed.content.splitlines():
        match = re.search(r"^- \[[ x]\] (.+) \(id: ([^)]+)\)$", line)
        if match and (target in match.group(1).casefold() or match.group(1).casefold() in target):
            task_id = match.group(2)
            break
    if task_id is None:
        return TaskCommandOutcome(f"Tâche introuvable dans Soul : {value}.", False)
    result = await task_tool.execute(  # type: ignore[attr-defined]
        action="update" if action == "complete" else "delete",
        task_id=task_id,
        **({"done": True} if action == "complete" else {}),
    )
    return TaskCommandOutcome(result.content, not result.is_error)


class SoulTasksTool(Tool):
    name = "soul_tasks"
    description = (
        "Gère la liste canonique de tâches Holmes dans Soul. Utilise action=list pour lire, "
        "create pour ajouter, update pour renommer ou terminer, delete pour supprimer."
    )
    input_schema = {  # noqa: RUF012
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "create", "update", "delete"]},
            "task_id": {"type": "string", "description": "Identifiant retourné par list."},
            "text": {"type": "string", "description": "Texte de la tâche."},
            "done": {"type": "boolean", "description": "État terminé ou non."},
        },
        "required": ["action"],
    }

    def __init__(self, store: CanonicalTaskStore) -> None:
        self._store = store

    async def execute(self, **kwargs: object) -> ToolResult:
        action = str(kwargs.get("action", "list"))
        try:
            if action == "list":
                tasks = await self._store.list_tasks()
                if not tasks:
                    return ToolResult("Aucune tâche dans Soul.")
                return ToolResult(
                    "\n".join(
                        f"- [{'x' if task.done else ' '}] {task.text} (id: {task.id})"
                        for task in tasks
                    )
                )
            if action == "create":
                task = await self._store.create_task(str(kwargs.get("text", "")))
                return ToolResult(f"Tâche ajoutée dans Soul : {task.text} (id: {task.id})")
            task_id = str(kwargs.get("task_id", "")).strip()
            if not task_id:
                return ToolResult("task_id est requis pour cette action.", is_error=True)
            if action == "update":
                text = kwargs.get("text")
                done = kwargs.get("done")
                task = await self._store.update_task(
                    task_id,
                    text=str(text) if text is not None else None,
                    done=bool(done) if done is not None else None,
                )
                return ToolResult(f"Tâche mise à jour : {task.text}")
            if action == "delete":
                deleted = await self._store.delete_task(task_id)
                return ToolResult(
                    "Tâche supprimée." if deleted else "Tâche introuvable.",
                    not deleted,
                )
            return ToolResult(f"Action inconnue : {action}", is_error=True)
        except (KeyError, ValueError) as exc:
            return ToolResult(str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001 — erreur Soul rendue au modèle
            return ToolResult(f"Erreur Soul : {exc}", is_error=True)
