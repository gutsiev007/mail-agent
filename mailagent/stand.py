"""Локальный стенд: данные компании, исходящие письма, заявки, очередь человека.

Состояние одной попытки сохраняется в JSON после каждого изменения,
поэтому его можно проверить после запуска и восстановить после «перезапуска».
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path


class AckLost(Exception):
    """Отправка выполнена, но подтверждение не дошло до вызывающего кода."""


def _set_path(obj: dict, dotted: str, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        obj = obj[k]
    obj[keys[-1]] = value


class Stand:
    def __init__(self, world: dict, env: dict | None = None, state_path: Path | None = None):
        env = env or {}
        self.world = copy.deepcopy(world)
        for path, value in (env.get("patch") or {}).items():
            _set_path(self.world, path, value)
        # faults: {"get_order": "unavailable" | "unavailable_once", "forward_message": "lost_ack"}
        self.faults = dict(env.get("faults") or {})
        self.state_path = Path(state_path) if state_path else None
        self.state = {
            "outbox": [],            # пересылки, уточнения клиенту
            "tickets_created": [],
            "ticket_updates": [],
            "human_queue": [],
            "blocked": [],           # попытки, отклонённые проверками кода
            "idempotency": {},       # key -> id эффекта
        }
        if self.state_path and self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._save()

    # ---------- сбои ----------
    def take_fault(self, tool: str) -> str | None:
        mode = self.faults.get(tool)
        if mode and mode.endswith("_once"):
            del self.faults[tool]
        return mode

    # ---------- запись ----------
    def _save(self):
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def find_by_key(self, key: str):
        eff_id = self.state["idempotency"].get(key)
        if not eff_id:
            return None
        for coll in ("outbox", "tickets_created", "ticket_updates", "human_queue"):
            for item in self.state[coll]:
                if item["id"] == eff_id:
                    return item
        return None

    def _add(self, coll: str, prefix: str, key: str, item: dict) -> dict:
        item = {"id": f"{prefix}-{len(self.state[coll]) + 1}", "ts": round(time.time(), 3), **item}
        self.state[coll].append(item)
        self.state["idempotency"][key] = item["id"]
        self._save()
        return item

    def send(self, key: str, kind: str, to: str, payload: dict) -> dict:
        """kind: forward | clarification. Сначала запись, потом «доставка»."""
        item = self._add("outbox", "OUT", key, {"kind": kind, "to": to, "delivery": "delivered", **payload})
        if self.take_fault("send") == "lost_ack":
            raise AckLost(item["id"])
        return item

    def create_ticket(self, key: str, payload: dict) -> dict:
        item = self._add("tickets_created", "T-NEW", key, {"status": "open", **payload})
        self.world["tickets"][item["id"]] = {
            "customer_id": payload["customer_id"], "status": "open",
            "assignee": payload["assignee"], "subject": payload["summary"], "last_update": "today",
        }
        return item

    def append_ticket(self, key: str, payload: dict) -> dict:
        return self._add("ticket_updates", "UPD", key, payload)

    def escalate(self, key: str, payload: dict) -> dict:
        return self._add("human_queue", "HUM", key, payload)

    def block(self, payload: dict):
        self.state["blocked"].append({"ts": round(time.time(), 3), **payload})
        self._save()

    # ---------- итог для проверки ----------
    def effects(self) -> list[dict]:
        out = []
        for m in self.state["outbox"]:
            out.append({"type": m["kind"], "role": m.get("recipient_role"), "ref": m.get("ref"),
                        "to": m["to"], "id": m["id"]})
        for t in self.state["tickets_created"]:
            out.append({"type": "create_ticket", "role": t["recipient_role"], "ref": t.get("contract_id"),
                        "to": t["assignee_address"], "id": t["id"]})
        for u in self.state["ticket_updates"]:
            out.append({"type": "append_ticket", "ticket_id": u["ticket_id"], "to": u["notified"], "id": u["id"]})
        for h in self.state["human_queue"]:
            out.append({"type": "escalate", "id": h["id"], "to": h["to"]})
        return out
