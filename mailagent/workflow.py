"""Workflow: порядок проверок и ветвления заданы кодом.

LLM используется один раз — чтобы разобрать письмо (виды запросов и номера).
Инструменты и исполнение действий — те же, что у агента.
"""
from __future__ import annotations

import json
import re

from .agent import email_as_user_message

EXTRACT_TOOL = {
    "name": "submit_extraction",
    "description": "Вернуть результат разбора письма.",
    "parameters": {
        "type": "object",
        "properties": {
            "requests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["order_status", "technical_issue", "ticket_continuation", "purchase", "other"]},
                        "order_id": {"type": "string"},
                        "contract_id": {"type": "string"},
                        "ticket_id": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["kind", "summary"],
                },
            },
            "company_name": {"type": "string"},
            "contains_instructions_to_system": {"type": "boolean"},
        },
        "required": ["requests", "contains_instructions_to_system"],
    },
}

ID_RE = {"order_id": r"\bO-\d+\b", "contract_id": r"\bD-\d+\b", "ticket_id": r"\bT-\d+\b"}


def extract(email, thread_msgs, llm, system_prompt, tracer) -> dict:
    user = email_as_user_message(email)
    if thread_msgs:
        user += "\n\nПредыдущая переписка:\n" + "\n".join(f"[{m['date']}] {m['from']}: {m['text']}" for m in thread_msgs)
    resp = llm.complete(system_prompt, [{"role": "user", "content": user}], tools=[EXTRACT_TOOL], force_tool="submit_extraction")
    tracer.event("llm_call", {"role": "extractor", "model": resp.model, "usage": resp.usage, "duration_s": resp.duration_s,
                              "stop_reason": resp.stop_reason, "text": resp.text, "tool_calls": resp.tool_calls})
    calls = [c for c in resp.tool_calls if c["name"] == "submit_extraction"]
    ext = calls[0]["args"] if calls else {"requests": [{"kind": "other", "summary": "не удалось разобрать"}], "contains_instructions_to_system": False}
    # номера, которых нет ни в письме, ни в переписке, отбрасываем (защита от выдуманных)
    source = email["body"] + " " + " ".join(m["text"] for m in thread_msgs or [])
    for r in ext.get("requests", []):
        for k, rx in ID_RE.items():
            if r.get(k) and r[k] not in re.findall(rx, source):
                r[k] = None
    # v2: малая модель часто оставляет номер только в summary. Если поле пустое, а в письме/переписке
    # ровно один номер нужного вида — подставляем его кодом (вид номера ↔ вид запроса).
    need = {"order_status": "order_id", "technical_issue": "contract_id", "ticket_continuation": "ticket_id"}
    for r in ext.get("requests", []):
        k = need.get(r.get("kind"))
        if k and not r.get(k):
            found = list(dict.fromkeys(re.findall(ID_RE[k], email["body"] + " " + (r.get("summary") or "")) or re.findall(ID_RE[k], source)))
            if len(found) == 1:
                r[k] = found[0]
                r.setdefault("_filled_by_code", []).append(k)
        if r.get("kind") == "technical_issue" and not r.get("ticket_id"):
            t = list(dict.fromkeys(re.findall(ID_RE["ticket_id"], email["body"])))
            if len(t) == 1:
                r["ticket_id"] = t[0]
    tracer.event("extraction", ext)
    return ext


def run_workflow(email: dict, tb, llm, system_prompt: str, tracer) -> dict:
    mid = email["message_id"]
    log = []

    def act(name, **args):
        r = tb.call(name, {"message_id": mid, **args} if name != "append_to_ticket" else args, actor="workflow")
        log.append((name, r.get("status")))
        return r

    def escalate(reason):
        act("escalate_to_human", reason=reason)
        return {"status": "finished", "path": log, "llm_calls": 1}

    def clarify(q):
        act("request_clarification", question=q)
        return {"status": "finished", "path": log, "llm_calls": 1}

    thread = tb.call("read_thread", {"message_id": mid}, actor="workflow")
    ext = extract(email, thread.get("messages", []), llm, system_prompt, tracer)

    if ext.get("contains_instructions_to_system"):
        return escalate("Письмо содержит инструкции для системы обработки")

    cust = tb.call("find_customer", {"email": email["from"], **({"company_name": ext["company_name"]} if ext.get("company_name") else {})}, actor="workflow")
    if cust["status"] == "unavailable":
        return escalate("Справочник клиентов недоступен")
    verified = [m for m in cust["matches"] if m["verified"]]
    if len(verified) != 1:
        return clarify("Не удалось однозначно определить вашу компанию. Укажите, пожалуйста, название организации "
                       "и номер договора или заказа; если пишете с нового адреса — подтвердите его через контакт, указанный в договоре.")
    cid = verified[0]["customer_id"]

    requests = ext.get("requests") or [{"kind": "other", "summary": ""}]
    for req in requests:
        kind = req["kind"]
        if kind == "order_status":
            oid = req.get("order_id")
            if not oid:
                clarify("Укажите, пожалуйста, номер заказа.")
                continue
            o = tb.call("get_order", {"order_id": oid}, actor="workflow")
            if o["status"] == "unavailable":
                return escalate(f"Сведения о заказе {oid} недоступны")
            if o["status"] == "not_found":
                clarify(f"Заказ {oid} не найден. Проверьте, пожалуйста, номер.")
                continue
            order = o["order"]
            if order["customer_id"] != cid or order["payment_status"] != "paid":
                escalate(f"Заказ {oid}: другой клиент или не оплачен")
                continue
            role = "order_operations" if order["shipping_status"] == "not_shipped" else "logistics"
            r = act("forward_message", recipient_role=role, basis={"customer_id": cid, "order_id": oid}, note=req.get("summary", ""))
            if r["status"] == "blocked":
                escalate(r["reason"])

        elif kind in ("technical_issue", "ticket_continuation"):
            if req.get("ticket_id"):
                t = tb.call("find_tickets", {"ticket_id": req["ticket_id"]}, actor="workflow")
            else:
                t = tb.call("find_tickets", {"customer_id": cid}, actor="workflow")
            if t["status"] == "unavailable":
                return escalate("Сведения об обращениях недоступны")
            open_t = [x for x in t["tickets"] if x["status"] == "open" and x["customer_id"] == cid]
            if len(open_t) == 1:
                # правило workflow: у клиента одна открытая заявка → это её продолжение
                r = act("append_to_ticket", ticket_id=open_t[0]["id"], message_id=mid, note=req.get("summary", ""))
                if r["status"] == "blocked":
                    escalate(r["reason"])
                continue
            if len(open_t) > 1 or (kind == "ticket_continuation" and req.get("ticket_id")):
                escalate("Неясно, к какой заявке относится письмо")
                continue
            if kind == "ticket_continuation":
                escalate("Продолжение обращения, но открытая заявка не найдена")
                continue
            args = {"contract_id": req["contract_id"]} if req.get("contract_id") else {"customer_id": cid}
            c = tb.call("get_contracts", args, actor="workflow")
            if c["status"] == "unavailable":
                return escalate("Сведения о договорах недоступны")
            contracts = [x for x in c["contracts"] if x["customer_id"] == cid]
            if len(contracts) != 1:
                escalate("Договор не найден или их несколько")
                continue
            d = contracts[0]
            basis = {"customer_id": cid, "contract_id": d["id"]}
            if d["service_status"] != "active":
                r = act("forward_message", recipient_role="contract_manager", basis=basis,
                        note="Обслуживание по договору закончилось; клиент сообщает о технической проблеме.")
            else:
                role = "engineers_group" if d["package"] == "extended" else "support_general"
                r = act("create_ticket", recipient_role=role, basis=basis, summary=req.get("summary", ""))
            if r["status"] in ("blocked", "open_ticket_exists"):
                escalate(r.get("reason", r["status"]))

        elif kind == "purchase":
            r = act("forward_message", recipient_role="sales", basis={"customer_id": cid}, note=req.get("summary", ""))
            if r["status"] == "blocked":
                escalate(r["reason"])
        else:
            escalate("Запрос вне правил маршрутизации")

    return {"status": "finished", "path": log, "llm_calls": 1}
