"""Запуск набора писем в одном или обоих режимах с чистым состоянием на каждую попытку."""
from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path

from .agent import run_agent
from .grader import grade
from .llm import make_llm
from .stand import Stand
from .tools import TOOLS_VERSION, RunContext, Toolbox
from .trace import Tracer
from .workflow import run_workflow

ROOT = Path(__file__).resolve().parent.parent


class CountingLLM:
    def __init__(self, inner):
        self.inner, self.calls, self.tin, self.tout = inner, 0, 0, 0
        self.model = getattr(inner, "model", "?")

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


def run_one(case, mode, trial, cfg, prompt_version, batch, batch_dir, world, llm_factory=None) -> dict:
    run_id = f"{batch}-{mode}-{case['case_id']}-try{trial}"
    agent_prompt = (ROOT / "prompts" / f"agent_{prompt_version}.md").read_text(encoding="utf-8")
    extractor_prompt = (ROOT / "prompts" / "extractor_p1.md").read_text(encoding="utf-8")
    role = "agent" if mode == "agent" else "extractor"
    base = {"run_id": run_id, "case_id": case["case_id"], "mode": mode,
            "prompt_version": prompt_version if mode == "agent" else "extractor_p1+wf2",
            "tools_version": TOOLS_VERSION, "code_version": code_version(), "dataset_version": dataset_version()}
    tracer = Tracer(batch_dir / "trace.jsonl", base)
    stand = Stand(world, case.get("env"), state_path=batch_dir / "state" / f"{run_id}.json")
    ctx = RunContext(case["email"])
    tb = Toolbox(stand, ctx, tracer)
    llm = CountingLLM(llm_factory(role) if llm_factory else make_llm(cfg[role]))
    tracer.event("run_start", {"email": case["email"], "env": case.get("env"), "trial": trial,
                               "model_config": cfg.get("name"), "models": {role: cfg.get(role, {}).get("model", llm.model)},
                               "limits": cfg.get("limits")})
    t0 = time.time()
    try:
        if mode == "agent":
            out = run_agent(case["email"], tb, llm, agent_prompt, tracer, cfg.get("limits", {}))
        else:
            out = run_workflow(case["email"], tb, llm, extractor_prompt, tracer)
    except Exception as e:  # технические ошибки остаются в общем числе попыток
        out = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        tracer.event("error", {"error": out["error"], "traceback": traceback.format_exc()[-1500:]})
    duration = round(time.time() - t0, 2)
    effects = stand.effects()
    g = grade(case, effects, stand.state["blocked"], out["status"])
    tool_calls = tb._n
    tracer.event("run_end", {"status": out["status"], "effects": g["effects"], "blocked": stand.state["blocked"],
                             "grade": {k: v for k, v in g.items() if k != "effects"}, "finish": out.get("finish"),
                             "duration_s": duration, "llm_calls": llm.calls, "tokens_in": llm.tin, "tokens_out": llm.tout})
    row = {"run_id": run_id, "case_id": case["case_id"], "set": case["set"], "path": case.get("path"),
           "mode": mode, "trial": trial, "prompt_version": base["prompt_version"], "model": llm.model,
           "duration_s": duration, "llm_calls": llm.calls, "tokens_in": llm.tin, "tokens_out": llm.tout,
           "tool_calls": tool_calls, **g}
    with (batch_dir / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def run_batch(cases, modes, trials, cfg, prompt_version, batch, runs_dir=None, llm_factory=None, quiet=False):
    batch_dir = Path(runs_dir or ROOT / "runs") / batch
    batch_dir.mkdir(parents=True, exist_ok=True)
    world = json.loads((ROOT / "data" / "world.json").read_text(encoding="utf-8"))
    (batch_dir / "meta.json").write_text(json.dumps({
        "batch": batch, "modes": modes, "trials": trials, "prompt_version": prompt_version,
        "config": {k: v for k, v in cfg.items()}, "tools_version": TOOLS_VERSION,
        "code_version": code_version(), "dataset_version": dataset_version(),
        "cases": [c["case_id"] for c in cases], "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for c in cases:
        for m in modes:
            for t in range(1, trials + 1):
                r = run_one(c, m, t, cfg, prompt_version, batch, batch_dir, world, llm_factory)
                rows.append(r)
                if not quiet:
                    eff = "; ".join(f"{e['type']}:{e.get('role') or e.get('ticket_id') or ''}{'/' + e['ref'] if e.get('ref') else ''}" for e in r["effects"]) or "—"
                    print(f"{'OK ' if r['correct'] else 'BAD'} {m:<8} {c['case_id']:<16} try{t} [{r['run_status']}] {eff}"
                          f"{'  blocked=' + str(r['blocked_attempts']) if r['blocked_attempts'] else ''}")
    return batch_dir, rows
