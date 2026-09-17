"""Outil vocal et conversationnel pour la liste canonique de tâches Soul."""

from __future__ import annotations

from jarvis.capabilities.tools.base import Tool, ToolResult
from jarvis.kernel.contracts import CanonicalTaskStore


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
