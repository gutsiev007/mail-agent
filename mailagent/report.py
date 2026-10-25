"""Таблицы сравнения: по письмам, по режимам, pass@k / pass^k, сравнение двух версий."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def load_rows(batch_dir: Path) -> list[dict]:
    p = Path(batch_dir) / "results.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _eff(effects) -> str:
    if not effects:
        return "нет действий"
    return ", ".join(f"{e['type']}" + (f"→{e['role']}" if e.get("role") and e["type"] != "clarification" else "")
                     + (f" {e['ticket_id']}" if e.get("ticket_id") else "") + (f" ({e['ref']})" if e.get("ref") else "")
                     for e in effects)


def _expected(case) -> str:
    return " ИЛИ ".join(_eff([{**p, "to": ""} for p in s]) for s in case["expected"]["any_of"])


def _rate(n, d) -> str:
    return f"{n}/{d}" if d else "н/о"


def summary(rows: list[dict]) -> dict:
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case_id"]].append(r["correct"])
    n = len(rows)
    human = sum(r["human_handoffs"] > 0 for r in rows)
    return {
        "correct": f"{sum(r['correct'] for r in rows)}/{n}",
        "pass_at_k": _rate(sum(any(v) for v in by_case.values()), len(by_case)),
        "pass_all_k": _rate(sum(all(v) for v in by_case.values()), len(by_case)),
        "k": max((len(v) for v in by_case.values()), default=0),
        "forbidden": sum(r["forbidden_executed"] for r in rows),
        "blocked": sum(r["blocked_attempts"] for r in rows),
        "false_routes": f"{sum(r['false_routes'] for r in rows)} из {sum(r['routing_actions'] for r in rows)}",
        "false_refusals": sum(r["false_refusal"] for r in rows),
        "human": _rate(human, n),
        "human_justified": _rate(sum(r["human_justified"] for r in rows), human),
        "limits": sum(r["run_status"] in ("step_limit", "time_limit", "no_finish") for r in rows),
        "errors": sum(r["run_status"] == "error" for r in rows),
        "avg_llm_calls": round(sum(r["llm_calls"] for r in rows) / n, 2) if n else 0,
        "avg_tool_calls": round(sum(r["tool_calls"] for r in rows) / n, 2) if n else 0,
        "avg_tokens_in": round(sum(r["tokens_in"] for r in rows) / n) if n else 0,
        "avg_tokens_out": round(sum(r["tokens_out"] for r in rows) / n) if n else 0,
        "avg_time_s": round(sum(r["duration_s"] for r in rows) / n, 2) if n else 0,
    }


METRICS = [
    ("correct", "Правильно обработано (все попытки)"), ("pass_at_k", "pass@k (по письмам)"), ("pass_all_k", "pass^k (по письмам)"),
    ("forbidden", "Выполнено запрещённых действий"), ("blocked", "Заблокировано кодом попыток"),
    ("false_routes", "Ложные пересылки/заявки из всех"), ("false_refusals", "Ложные отказы"),
    ("human", "Передачи человеку"), ("human_justified", "Из них оправданных"), ("limits", "Остановки по лимиту"),
    ("errors", "Технические ошибки"), ("avg_llm_calls", "Вызовов модели на письмо"), ("avg_tool_calls", "Вызовов инструментов на письмо"),
    ("avg_tokens_in", "Входных токенов на письмо"), ("avg_tokens_out", "Выходных токенов на письмо"), ("avg_time_s", "Время на письмо, с"),
]


def build_report(batch_dir: Path, cases_by_id: dict) -> str:
    rows = load_rows(batch_dir)
    modes = sorted({r["mode"] for r in rows}, key=lambda m: m != "workflow")
    sets = sorted({r["set"] for r in rows})
    out = [f"# Отчёт по запуску `{Path(batch_dir).name}`\n"]
    meta_p = Path(batch_dir) / "meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        cfg = meta["config"]
        out.append(f"Модели: workflow-извлечение — `{cfg.get('extractor', {}).get('model')}`, агент — `{cfg.get('agent', {}).get('model')}`; "
                   f"промпт агента `{meta['prompt_version']}`, инструменты `{meta['tools_version']}`, код `{meta['code_version']}`, "
                   f"данные `{meta['dataset_version']}`, попыток на письмо: {meta['trials']}.\n")
    for s in sets:
        out.append(f"\n## Письма: {s}\n")
        out.append("| Письмо | Путь | Ожидаемый итог | " + " | ".join(f"{m}: факт. действие" for m in modes) + " |")
        out.append("|---|---|---|" + "---|" * len(modes))
        for cid in dict.fromkeys(r["case_id"] for r in rows if r["set"] == s):
            case = cases_by_id.get(cid, {})
            cells = []
            for m in modes:
                rr = sorted([r for r in rows if r["case_id"] == cid and r["mode"] == m], key=lambda r: r["trial"])
                if not rr:
                    cells.append("—")
                    continue
                marks = "".join("✓" if r["correct"] else "✗" for r in rr)
                distinct = list(dict.fromkeys(_eff(r["effects"]) for r in rr))
                extra = f" [{rr[0]['run_status']}]" if rr[0]["run_status"] != "finished" else ""
                cells.append(f"{marks} {' / '.join(distinct)}{extra}")
            out.append(f"| {cid} | {case.get('path', '')} | {_expected(case) if case else ''} | " + " | ".join(cells) + " |")
        out.append("\n| Показатель | " + " | ".join(modes) + " |")
        out.append("|---|" + "---|" * len(modes))
        sm = {m: summary([r for r in rows if r["set"] == s and r["mode"] == m]) for m in modes}
        for key, title in METRICS:
            out.append(f"| {title} | " + " | ".join(str(sm[m][key]) for m in modes) + " |")
    return "\n".join(out) + "\n"


def compare(batch_a: Path, batch_b: Path, mode: str) -> str:
    ra = [r for r in load_rows(batch_a) if r["mode"] == mode]
    rb = [r for r in load_rows(batch_b) if r["mode"] == mode]
    sa, sb = summary(ra), summary(rb)

    def per_case(rows):
        d = defaultdict(list)
        for r in rows:
            d[r["case_id"]].append(r["correct"])
        return {k: sum(v) / len(v) for k, v in d.items()}

    ca, cb = per_case(ra), per_case(rb)
    fixed = [c for c in cb if cb[c] > ca.get(c, 0)]
    broke = [c for c in cb if cb[c] < ca.get(c, 1)]
    out = [f"# Сравнение версий ({mode}): `{Path(batch_a).name}` → `{Path(batch_b).name}`\n",
           "| Показатель | До | После |", "|---|---|---|"]
    for key, title in METRICS:
        out.append(f"| {title} | {sa[key]} | {sb[key]} |")
    out.append(f"\nСтало лучше: {', '.join(fixed) or 'нет'}\n\nСтало хуже: {', '.join(broke) or 'нет'}\n")
    return "\n".join(out)
