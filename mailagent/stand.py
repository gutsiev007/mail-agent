"""Локальный стенд: данные компании, исходящие письма, заявки, очередь человека.

Два вида данных и один источник истины для каждого (решение 02):
- world — базовые бизнес-данные (world.json + env.patch), только для чтения;
- state — журнал эффектов этой попытки (outbox, созданные заявки, дополнения, очередь человека).
Созданные заявки живут только в state; поиск заявок объединяет базу и state (all_tickets).

state пишется атомарно (решение E4): временный файл → fsync → os.replace.
"""
from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path


class AckLost(Exception):
    """Отправка выполнена, но подтверждение не дошло до вызывающего кода."""


class StateCorrupted(Exception):
    """Файл состояния повреждён и не может быть загружен."""


def _set_path(obj: dict, dotted: str, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        obj = obj[k]
    obj[keys[-1]] = value


def atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


EMPTY_STATE = {
    "outbox": [],            # пересылки, уточнения клиенту
    "tickets_created": [],   # единственное место, где живут новые заявки
    "ticket_updates": [],
    "human_queue": [],
    "blocked": [],           # попытки, отклонённые проверками кода
    "idempotency": {},       # key -> id эффекта
}


class Stand:
    def __init__(self, world: dict, env: dict | None = None, state_path: Path | None = None):
        env = env or {}
        self.world = copy.deepcopy(world)
        for path, value in (env.get("patch") or {}).items():
            _set_path(self.world, path, value)
        # faults: {"get_order": "unavailable" | "unavailable_once", "send": "lost_ack"}
        self.faults = dict(env.get("faults") or {})
        self.state_path = Path(state_path) if state_path else None
        self.state = copy.deepcopy(EMPTY_STATE)
        if self.state_path and self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise StateCorrupted(f"Файл состояния {self.state_path} повреждён: {e}. "
                                     "Эффекты этой попытки нельзя восстановить автоматически — проверь outbox вручную.") from None
        self._save()

    # ---------- сбои ----------
    def take_fault(self, tool: str) -> str | None:
        mode = self.faults.get(tool)
        if mode and mode.endswith("_once"):
            del self.faults[tool]
        return mode

    # ---------- исполнители ----------
    def resolve_assignee(self, assignee: dict) -> str | None:
        """{kind, id} → адрес в момент уведомления (решение 03). None — исполнитель не найден."""
        kind, ident = assignee.get("kind"), assignee.get("id")
        if kind == "staff":
            return self.world["staff"].get(ident)
        if kind == "group":
            return self.world["engineer_groups"].get(ident)
        if kind == "queue":
            d = self.world["directory"].get(ident)
            return d["address"] if d else None
        return None

    # ---------- заявки: база + журнал ----------
    def all_tickets(self) -> dict:
        tickets = {tid: dict(t) for tid, t in self.world["tickets"].items()}
        for t in self.state["tickets_created"]:
            tickets[t["id"]] = {"customer_id": t["customer_id"], "status": "open", "assignee": t["assignee"],
                                "subject": t["summary"], "last_update": "new", "contract_id": t.get("contract_id")}
        return tickets

    # ---------- запись ----------
    def _save(self):
        if self.state_path:
            atomic_write(self.state_path, json.dumps(self.state, ensure_ascii=False, indent=2))

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
        return self._add("tickets_created", "T-NEW", key, {"status": "open", **payload})

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
                        "to": t["notified"], "id": t["id"]})
        for u in self.state["ticket_updates"]:
            out.append({"type": "append_ticket", "ticket_id": u["ticket_id"], "to": u["notified"], "id": u["id"]})
        for h in self.state["human_queue"]:
            out.append({"type": "escalate", "id": h["id"], "to": h["to"]})
        return out
