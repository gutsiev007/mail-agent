"""Запуск набора писем в одном или обоих режимах с чистым состоянием на каждую попытку.

Статусы попытки:
- finished, step_limit, time_limit, no_finish — работа модели/кода (входят в метрики);
- internal_error — ошибка программы (входит в метрики, отдельный счётчик);
- infra_error — недоступна модель/сервер (НЕ входит в знаменатель, решение E1).

После любой попытки «страховка» кода: если письмо осталось без действия или попытка оборвалась,
код сам передаёт его человеку (решение «после P1»: finish без действий / лимит шагов).
"""
from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path

from .agent import run_agent
from .grader import grade
from .llm import LLMError, make_llm
from .stand import Stand
from .tools import TOOLS_VERSION, RunContext, Toolbox, _key
from .trace import Tracer
from .workflow import WORKFLOW_VERSION, run_workflow

ROOT = Path(__file__).resolve().parent.parent
MAX_CONSECUTIVE_INFRA = 3


class BatchAborted(Exception):
    pass


class CountingLLM:
    def __init__(self, inner):
        self.inner, self.calls, self.tin, self.tout = inner, 0, 0, 0
        self.model = getattr(inner, "model", "?")

    @property
    def last_request(self):
        return getattr(self.inner, "last_request", None)

    def complete(self, *a, **kw):
        r = self.inner.complete(*a, **kw)
        self.calls += 1
        self.tin += r.usage.get("input") or 0
        self.tout += r.usage.get("output") or 0
        return r


def _hash_files(paths) -> str:
    h = hashlib.sha1()
    for p in sorted(paths):
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:10]


def code_version() -> str:
    return _hash_files((ROOT / "mailagent").glob("*.py"))


def dataset_version() -> str:
    return _hash_files([ROOT / "data" / "world.json", *(ROOT / "cases").glob("*.json")])


def prompt_ref(name: str) -> str:
    p = ROOT / "prompts" / f"{name}.md"
    return f"{name}@{_hash_files([p])[:6]}"


def config_hash(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]


def load_cases(sets: list[str], only: list[str] | None = None) -> list[dict]:
    cases = []
    for s in sets:
        p = ROOT / "cases" / f"{s}.json"
        if not p.exists():
            raise SystemExit(f"Нет файла {p}")
        for c in json.loads(p.read_text(encoding="utf-8")):
            c["set"] = s
            cases.append(c)
    if only:
        cases = [c for c in cases if c["case_id"] in only]
    return cases


def _guard(stand: Stand, tracer, status: str, email: dict):
    """Письмо не должно остаться без хозяина: незавершённое или пустое → человеку (действие кода)."""
    effects = stand.effects()
    if status == "finished" and effects:
        return False
    if any(e["type"] == "escalate" for e in effects):
        return False
    key = _key("escalate", email["message_id"])
    if stand.find_by_key(key):
        return False
    reason = {"finished": "обработка завершена без действий"}.get(status, f"обработка не завершена: {status}")
    item = stand.escalate(key, {"message_id": email["message_id"], "reason": reason, "actor": "code_guard",
                                "partial_effects": [e["type"] for e in effects],
                                "to": stand.world["directory"]["human_triage"]["address"]})
    tracer.event("guard_escalation", {"reason": reason, "queue_id": item["id"], "partial_effects": len(effects)})
    return True


def run_one(case, mode, trial, cfg, prompt_version, batch, batch_dir, world, llm_factory=None, run_suffix="") -> dict:
    run_id = f"{batch}-{mode}-{case['case_id']}-try{trial}{run_suffix}"
    agent_prompt = (ROOT / "prompts" / f"agent_{prompt_version}.md").read_text(encoding="utf-8")
    extractor_prompt = (ROOT / "prompts" / "extractor_p1.md").read_text(encoding="utf-8")
    continuation_prompt = (ROOT / "prompts" / "continuation_p1.md").read_text(encoding="utf-8")
    role = "agent" if mode == "agent" else "extractor"
    pv = prompt_ref(f"agent_{prompt_version}") if mode == "agent" else \
        f"{prompt_ref('extractor_p1')}+{prompt_ref('continuation_p1')}+{WORKFLOW_VERSION}"
    base = {"run_id": run_id, "case_id": case["case_id"], "mode": mode, "prompt_version": pv,
            "tools_version": TOOLS_VERSION, "code_version": code_version(), "dataset_version": dataset_version()}
    tracer = Tracer(batch_dir / "trace.jsonl", base)
    stand = Stand(world, case.get("env"), state_path=batch_dir / "state" / f"{run_id}.json")
    ctx = RunContext(case["email"])
    tb = Toolbox(stand, ctx, tracer)
    llm = CountingLLM(llm_factory(role) if llm_factory else make_llm(cfg[role]))
    limits = cfg.get("limits", {})
    tracer.event("run_start", {"email": case["email"], "env": case.get("env"), "trial": trial,
                               "model_config": cfg.get("name"), "config_hash": config_hash(cfg),
                               "models": {role: cfg.get(role, {}).get("model", llm.model)},
                               "temperature": cfg.get(role, {}).get("temperature"), "limits": limits})
    t0 = time.time()
    deadline = t0 + limits.get("max_seconds", 180)
    try:
        if mode == "agent":
            out = run_agent(case["email"], tb, llm, agent_prompt, tracer, limits, deadline=deadline)
        else:
            out = run_workflow(case["email"], tb, llm, extractor_prompt, tracer, continuation_prompt, deadline=deadline)
    except LLMError as e:
        status = "time_limit" if e.kind == "timeout" else "infra_error"
        out = {"status": status, "error": f"{e.kind}: {e}"}
        # полный запрос пишем только для упавших попыток (решение E3)
        tracer.event("infra_error" if status == "infra_error" else "time_limit",
                     {"error": out["error"], "request": llm.last_request})
    except Exception as e:  # ошибка программы
        out = {"status": "internal_error", "error": f"{type(e).__name__}: {e}"}
        tracer.event("internal_error", {"error": out["error"], "traceback": traceback.format_exc()[-2000:]})
    if out["status"] != "infra_error":
        _guard(stand, tracer, out["status"], case["email"])
    duration = round(time.time() - t0, 2)
    effects = stand.effects()
    g = grade(case, effects, stand.state["blocked"], out["status"])
    guard_used = any(h.get("actor") == "code_guard" for h in stand.state["human_queue"])
    tracer.event("run_end", {"status": out["status"], "effects": g["effects"], "blocked": stand.state["blocked"],
                             "grade": {k: v for k, v in g.items() if k != "effects"}, "finish": out.get("finish"),
                             "guard_escalation": guard_used, "internal_errors": tb.internal_errors,
                             "duration_s": duration, "llm_calls": llm.calls, "tokens_in": llm.tin, "tokens_out": llm.tout})
    row = {"run_id": run_id, "case_id": case["case_id"], "set": case["set"], "path": case.get("path"),
           "mode": mode, "trial": trial, "prompt_version": pv, "model": llm.model,
           "duration_s": duration, "llm_calls": llm.calls, "tokens_in": llm.tin, "tokens_out": llm.tout,
           "tool_calls": tb._n, "guard_escalation": guard_used,
           "internal_errors": tb.internal_errors + (1 if out["status"] == "internal_error" and not tb.internal_errors else 0),
           **g}
    with (batch_dir / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def completed_attempts(batch_dir: Path) -> set:
    """(mode, case_id, trial) попыток, завершённых не из-за инфраструктуры — их --resume пропускает."""
    p = batch_dir / "results.jsonl"
    done = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[(r["mode"], r["case_id"], r["trial"])] = r["run_status"]
    return {k for k, v in done.items() if v != "infra_error"}


def run_batch(cases, modes, trials, cfg, prompt_version, batch, runs_dir=None, llm_factory=None, quiet=False, resume=False):
    batch_dir = Path(runs_dir or ROOT / "runs") / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    world = json.loads((ROOT / "data" / "world.json").read_text(encoding="utf-8"))
    skip = completed_attempts(batch_dir) if resume else set()
    meta_p = batch_dir / "meta.json"
    if not (resume and meta_p.exists()):
        meta_p.write_text(json.dumps({
            "batch": batch, "modes": modes, "trials": trials, "prompt_version": prompt_version,
            "config": cfg, "config_hash": config_hash(cfg), "tools_version": TOOLS_VERSION,
            "workflow_version": WORKFLOW_VERSION, "code_version": code_version(), "dataset_version": dataset_version(),
            "cases": [c["case_id"] for c in cases], "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    rows, infra_streak = [], 0
    for c in cases:
        for m in modes:
            for t in range(1, trials + 1):
                if (m, c["case_id"], t) in skip:
                    continue
                suffix = f"-r{int(time.time())}" if resume else ""
                r = run_one(c, m, t, cfg, prompt_version, batch, batch_dir, world, llm_factory, suffix)
                rows.append(r)
                if not quiet:
                    eff = "; ".join(f"{e['type']}:{e.get('role') or e.get('ticket_id') or ''}{'/' + e['ref'] if e.get('ref') else ''}" for e in r["effects"]) or "—"
                    mark = "ERR" if r["run_status"] == "infra_error" else ("OK " if r["correct"] else "BAD")
                    print(f"{mark} {m:<8} {c['case_id']:<16} try{t} [{r['run_status']}] {eff}"
                          f"{'  blocked=' + str(r['blocked_attempts']) if r['blocked_attempts'] else ''}")
                infra_streak = infra_streak + 1 if r["run_status"] == "infra_error" else 0
                if infra_streak >= MAX_CONSECUTIVE_INFRA:
                    raise BatchAborted(
                        f"{MAX_CONSECUTIVE_INFRA} попытки подряд не дошли до модели (сервер или сеть). Батч остановлен. "
                        f"Исправь причину и продолжи: python3 -m mailagent run ... --batch {batch} --resume")
    return batch_dir, rows
