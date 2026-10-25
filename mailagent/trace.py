"""JSONL-трасса. Один формат для агента и workflow; одна строка — одно событие."""
from __future__ import annotations

import json
import time
from pathlib import Path


class Tracer:
    def __init__(self, path: Path, base: dict):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.base = base  # run_id, case_id, mode, prompt_version, tools_version, model_config, code_version, dataset_version
        self.index = 0

    def event(self, event_type: str, data: dict, **extra):
        self.index += 1
        rec = {**{k: self.base[k] for k in ("run_id", "case_id", "mode")},
               "event_index": self.index, "event_type": event_type, "ts": round(time.time(), 3),
               **{k: self.base[k] for k in ("prompt_version", "tools_version", "code_version", "dataset_version")},
               **extra, "data": data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_run(trace_path: Path, run_id: str) -> list[dict]:
    out = []
    with Path(trace_path).open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["run_id"] == run_id:
                out.append(rec)
    return out


def format_event(e: dict) -> str:
    d = e["data"]
    t = e["event_type"]
    head = f"#{e['event_index']:02d} {t:<12}"
    if t == "run_start":
        em = d["email"]
        return f"{head} {em['message_id']} from {em['from']}: {em['body'][:100]}  | models={d.get('models')}"
    if t == "llm_call":
        calls = ", ".join(f"{c['name']}({json.dumps(c['args'], ensure_ascii=False)[:120]})" for c in d.get("tool_calls", []))
        txt = (d.get("text") or "").replace("\n", " ")[:160]
        return (f"{head} [{d['role']}/{d['model']}] in={d['usage'].get('input')} out={d['usage'].get('output')} "
                f"{d['duration_s']}s → {calls or '-'} {('| ' + txt) if txt else ''}")
    if t == "tool_call":
        return f"{head} {e.get('call_id')} {d['actor']}: {d['tool']}({json.dumps(d['args'], ensure_ascii=False)})"
    if t == "tool_result":
        r = json.dumps(d["result"], ensure_ascii=False)
        return f"{head} {e.get('call_id')} {d['tool']} → {r[:300]}{' retries=' + str(d['retries']) if d['retries'] else ''}"
    return f"{head} {json.dumps(d, ensure_ascii=False)[:400]}"
