"""Workflow: порядок проверок и ветвления заданы кодом.

LLM используется для разбора письма (виды запросов) и — только когда у клиента есть открытая
заявка, а номер заявки в письме не назван, — для узкого вопроса «та же проблема / другая / неясно»
(решение 05). Инструменты и исполнение действий — те же, что у агента.
"""
from __future__ import annotations

import re

from .agent import wrap_email

WORKFLOW_VERSION = "wf3"  # wf3: номера только из текста письма; проверка продолжения заявки моделью; identify_sender

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

CONTINUATION_TOOL = {
    "name": "submit_continuation",
    "description": "Решение: письмо продолжает открытую заявку, описывает другую проблему или неясно.",
    "parameters": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["same", "different", "unclear"]},
            "ticket_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["decision", "reason"],
    },
}

ID_RE = {"order_id": r"\bO-\d+\b", "contract_id": r"\bD-\d+\b", "ticket_id": r"\bT-\d+\b"}
NEED = {"order_status": "order_id", "technical_issue": "contract_id", "ticket_continuation": "ticket_id"}


def _source_text(email: dict, thread_msgs: list) -> str:
    return " ".join([email.get("subject", ""), email.get("body", "")] + [m["text"] for m in thread_msgs or []])


def extract(email, thread_msgs, llm, system_prompt, tracer, deadline=None) -> dict:
    user = wrap_email(email)
    if thread_msgs:
        user += "\n\nПредыдущая переписка:\n" + "\n".join(f"[{m['date']}] {m['from']}: {m['text']}" for m in thread_msgs)
    resp = llm.complete(system_prompt, [{"role": "user", "content": user}], tools=[EXTRACT_TOOL],
                        force_tool="submit_extraction", deadline=deadline)
    tracer.event("llm_call", {"role": "extractor", "model": resp.model, "usage": resp.usage, "duration_s": resp.duration_s,
                              "stop_reason": resp.stop_reason, "request_hash": resp.request_hash,
                              "text": resp.text, "tool_calls": resp.tool_calls})
    calls = [c for c in resp.tool_calls if c["name"] == "submit_extraction" and isinstance(c["args"], dict)]
    ext = calls[0]["args"] if calls else {"requests": [{"kind": "other", "summary": "не удалось разобрать"}], "contains_instructions_to_system": False}
    # Решение 04: номер — только из текста (тема, тело, переписка). summary модели источником не является.
    source = _source_text(email, thread_msgs)
    for r in ext.get("requests", []):
        for k, rx in ID_RE.items():
            if r.get(k) and r[k] not in re.findall(rx, source):
                r.setdefault("_dropped_by_code", []).append(r[k])
                r[k] = None
        k = NEED.get(r.get("kind"))
        if k and not r.get(k):
            found = list(dict.fromkeys(re.findall(ID_RE[k], source)))
            if len(found) == 1:
                r[k] = found[0]
                r.setdefault("_filled_by_code", []).append(k)
        if r.get("kind") in ("technical_issue", "ticket_continuation") and not r.get("ticket_id"):
            t = list(dict.fromkeys(re.findall(ID_RE["ticket_id"], email.get("subject", "") + " " + email["body"])))
            if len(t) == 1:
                r["ticket_id"] = t[0]
    tracer.event("extraction", ext)
    return ext


def classify_continuation(email, open_tickets, llm, prompt, tracer, deadline=None) -> dict:
    listing = "\n".join(f"- {t['id']}: {t['subject']}" for t in open_tickets)
    user = wrap_email(email) + f"\n\nОткрытые заявки этого клиента:\n{listing}"
    resp = llm.complete(prompt, [{"role": "user", "content": user}], tools=[CONTINUATION_TOOL],
                        force_tool="submit_continuation", deadline=deadline)
    tracer.event("llm_call", {"role": "continuation", "model": resp.model, "usage": resp.usage, "duration_s": resp.duration_s,
                              "stop_reason": resp.stop_reason, "request_hash": resp.request_hash,
                              "text": resp.text, "tool_calls": resp.tool_calls})
    calls = [c for c in resp.tool_calls if c["name"] == "submit_continuation" and isinstance(c["args"], dict)]
    d = calls[0]["args"] if calls else {"decision": "unclear", "reason": "модель не дала ответ"}
    ids = {t["id"] for t in open_tickets}
    if d.get("decision") == "same" and d.get("ticket_id") not in ids:
        d = {"decision": "same", "ticket_id": next(iter(ids)), "reason": d.get("reason", "")} if len(ids) == 1 else \
            {"decision": "unclear", "reason": "модель назвала заявку не из списка"}
    if d.get("decision") not in ("same", "different", "unclear"):
        d = {"decision": "unclear", "reason": "неизвестное решение"}
    tracer.event("continuation", d)
    return d


def run_workflow(email: dict, tb, llm, system_prompt: str, tracer, continuation_prompt: str = "", deadline=None) -> dict:
    mid = email["message_id"]
    log = []
    llm_calls = 0

    def act(name, **args):
        r = tb.call(name, {"message_id": mid, **args} if name != "append_to_ticket" else args, actor="workflow")
        log.append((name, r.get("status")))
        return r

    def done(status="finished"):
        return {"status": status, "path": log, "llm_calls": llm_calls}

    def escalate(reason):
        act("escalate_to_human", reason=reason)
        return done()

    def clarify(q):
        act("request_clarification", question=q)
        return done()

    thread = tb.call("read_thread", {"message_id": mid}, actor="workflow")
    ext = extract(email, thread.get("messages", []), llm, system_prompt, tracer, deadline)
    llm_calls += 1

    if ext.get("contains_instructions_to_system"):
        return escalate("Письмо содержит инструкции для системы обработки")

    me = tb.call("identify_sender", {}, actor="workflow")
    if me["status"] == "unavailable":
        return escalate("Справочник клиентов недоступен")
    if me["status"] != "found":
        return clarify("Не удалось определить вашу компанию по адресу отправителя. Укажите, пожалуйста, название "
                       "организации и номер договора или заказа; если пишете с нового адреса — подтвердите его через "
                       "контакт, указанный в договоре.")
    cid = me["customer"]["customer_id"]

    requests = ext.get("requests") or [{"kind": "other", "summary": ""}]
    for req in requests:
        if tb.internal_errors:
            return done("internal_error")
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
                escalate(r["message"])

        elif kind in ("technical_issue", "ticket_continuation"):
            if req.get("ticket_id"):
                t = tb.call("find_tickets", {"ticket_id": req["ticket_id"]}, actor="workflow")
            else:
                t = tb.call("find_tickets", {"customer_id": cid}, actor="workflow")
            if t["status"] == "unavailable":
                return escalate("Сведения об обращениях недоступны")
            open_t = [x for x in t.get("tickets", []) if x["status"] == "open" and x["customer_id"] == cid]
            if req.get("ticket_id"):
                if len(open_t) == 1:  # номер заявки назван в письме — это продолжение без вопросов к модели
                    r = act("append_to_ticket", ticket_id=open_t[0]["id"], message_id=mid, note=req.get("summary", ""))
                    if r["status"] == "blocked":
                        escalate(r["message"])
                else:
                    escalate(f"Заявка {req['ticket_id']} не найдена, закрыта или принадлежит другому клиенту")
                continue
            if open_t:
                d = classify_continuation(email, open_t, llm, continuation_prompt, tracer, deadline)
                llm_calls += 1
                if d["decision"] == "same":
                    r = act("append_to_ticket", ticket_id=d["ticket_id"], message_id=mid, note=req.get("summary", ""))
                    if r["status"] == "blocked":
                        escalate(r["message"])
                    continue
                if d["decision"] == "unclear":
                    escalate(f"Неясно, продолжение ли это открытой заявки: {d.get('reason', '')}")
                    continue
                # different → обрабатываем как новую проблему
            if kind == "ticket_continuation" and not open_t:
                escalate("Продолжение обращения, но открытая заявка не найдена")
                continue
            args = {"contract_id": req["contract_id"]} if req.get("contract_id") else {"customer_id": cid}
            c = tb.call("get_contracts", args, actor="workflow")
            if c["status"] == "unavailable":
                return escalate("Сведения о договорах недоступны")
            contracts = [x for x in c.get("contracts", []) if x["customer_id"] == cid]
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
                r = act("create_ticket", recipient_role=role, basis=basis, summary=req.get("summary", ""),
                        confirm_new_issue=bool(open_t))
            if r["status"] in ("blocked", "open_ticket_exists"):
                escalate(r.get("message", r["status"]))

        elif kind == "purchase":
            r = act("forward_message", recipient_role="sales", basis={"customer_id": cid}, note=req.get("summary", ""))
            if r["status"] == "blocked":
                escalate(r["message"])
        else:
            escalate("Запрос вне правил маршрутизации")

    return done("internal_error" if tb.internal_errors else "finished")
