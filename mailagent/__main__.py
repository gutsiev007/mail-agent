"""CLI (кроссплатформенный, без .sh/.bat):
  python3 -m mailagent run --mode both --set dev --trials 3 --config config/models.local.json --prompt p3 --batch dev-v3
  python3 -m mailagent run ... --batch dev-v3 --resume   # продолжить прерванный батч, без дублей
  python3 -m mailagent suite --config config/models.local.json   # весь набор прогонов версии
  python3 -m mailagent show <run_id>            # все события одной попытки
  python3 -m mailagent effects <run_id>         # что реально сделано на стенде
  python3 -m mailagent report <batch>           # таблица по письмам и метрики
  python3 -m mailagent compare <batchA> <batchB> --mode agent
  python3 -m mailagent validate                 # проверить файлы кейсов
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .llm import LLMError, preflight
from .report import build_report, compare
from .runner import ROOT, BatchAborted, load_cases, run_batch
from .trace import format_event, load_run

RUNS = ROOT / "runs"

# Набор прогонов текущей версии. holdout запускается один раз, после фиксации версии.
SUITE = [
    {"batch": "dev-v3", "set": "dev", "mode": "both"},
    {"batch": "attacks-v3", "set": "attacks", "mode": "both"},
    {"batch": "new-v3", "set": "new", "mode": "both"},
    {"batch": "holdout-v3", "set": "holdout", "mode": "both"},
]


def _find_batch(run_id: str) -> Path:
    cands = [d for d in (RUNS.iterdir() if RUNS.exists() else [])
             if run_id.startswith(d.name + "-") and (d / "trace.jsonl").exists()]
    if not cands:
        raise SystemExit(f"Не найден запуск для {run_id}")
    return max(cands, key=lambda d: len(d.name))


def _all_cases():
    return {c["case_id"]: c for c in load_cases([p.stem for p in (ROOT / "cases").glob("*.json")])}


def _preflight(cfg, modes):
    for role in sorted({"agent" if m == "agent" else "extractor" for m in modes}):
        try:
            model = preflight(cfg[role])
            print(f"Проверка модели [{role}]: {cfg[role]['model']} отвечает ({model})")
        except LLMError as err:
            raise SystemExit(f"Модель [{role}] {cfg[role].get('model')} недоступна: {err}. "
                             "Запусти сервер (open -a Ollama) или проверь ключ и название модели. Батч не начат.")


def _run(cfg, sets, cases_only, modes, trials, prompt, batch, resume):
    cases = load_cases(sets, cases_only)
    if (RUNS / batch / "results.jsonl").exists() and not resume:
        raise SystemExit(f"Запуск {batch} уже есть. Продолжить: --resume; новый — другое имя --batch.")
    try:
        batch_dir, _ = run_batch(cases, modes, trials, cfg, prompt, batch, resume=resume)
    except BatchAborted as e:
        raise SystemExit(str(e))
    (batch_dir / "report.md").write_text(build_report(batch_dir, _all_cases()), encoding="utf-8")
    print(f"\nОтчёт: {batch_dir / 'report.md'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mailagent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--mode", choices=["agent", "workflow", "both"], default="both")
    r.add_argument("--set", default="dev", help="dev | new | attacks | holdout | dev,new")
    r.add_argument("--cases", default="", help="через запятую: mail-02,mail-07")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--config", default="config/models.local.json")
    r.add_argument("--prompt", default="p3")
    r.add_argument("--batch", required=True)
    r.add_argument("--resume", action="store_true", help="пропустить завершённые попытки, повторить infra_error")
    su = sub.add_parser("suite")
    su.add_argument("--config", default="config/models.local.json")
    su.add_argument("--prompt", default="p3")
    su.add_argument("--trials", type=int, default=3)
    su.add_argument("--resume", action="store_true")
    s = sub.add_parser("show"); s.add_argument("run_id")
    e = sub.add_parser("effects"); e.add_argument("run_id")
    rp = sub.add_parser("report"); rp.add_argument("batch")
    c = sub.add_parser("compare"); c.add_argument("a"); c.add_argument("b"); c.add_argument("--mode", default="agent")
    sub.add_parser("validate")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        cfg = json.loads((ROOT / a.config).read_text(encoding="utf-8"))
        modes = ["workflow", "agent"] if a.mode == "both" else [a.mode]
        _preflight(cfg, modes)
        _run(cfg, a.set.split(","), [x for x in a.cases.split(",") if x], modes, a.trials, a.prompt, a.batch, a.resume)
    elif a.cmd == "suite":
        cfg = json.loads((ROOT / a.config).read_text(encoding="utf-8"))
        _preflight(cfg, ["workflow", "agent"])
        for step in SUITE:
            done = (RUNS / step["batch"] / "results.jsonl").exists()
            if done and not a.resume:
                print(f"— {step['batch']} уже есть, пропускаю")
                continue
            print(f"\n=== {step['batch']} ===")
            _run(cfg, [step["set"]], [], ["workflow", "agent"], a.trials, a.prompt, step["batch"], done)
        if (RUNS / "dev-v2").exists() and (RUNS / "dev-v3").exists():
            for m in ("agent", "workflow"):
                (RUNS / f"compare_dev-v2_vs_dev-v3_{m}.md").write_text(compare(RUNS / "dev-v2", RUNS / "dev-v3", m), encoding="utf-8")
        print("\nГОТОВО. Заархивируй папку runs и пришли.")
    elif a.cmd == "show":
        for ev in load_run(_find_batch(a.run_id) / "trace.jsonl", a.run_id):
            print(format_event(ev))
    elif a.cmd == "effects":
        st = _find_batch(a.run_id) / "state" / f"{a.run_id}.json"
        print(st.read_text(encoding="utf-8"))
    elif a.cmd == "report":
        print(build_report(RUNS / a.batch, _all_cases()))
    elif a.cmd == "compare":
        txt = compare(RUNS / a.a, RUNS / a.b, a.mode)
        (RUNS / f"compare_{a.a}_vs_{a.b}.md").write_text(txt, encoding="utf-8")
        print(txt)
    elif a.cmd == "validate":
        ok = True
        for p in sorted((ROOT / "cases").glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            ids = set()
            for c in data:
                for k in ("case_id", "email", "expected"):
                    if k not in c:
                        print(f"{p.name}: {c.get('case_id')} нет поля {k}"); ok = False
                if c["case_id"] in ids:
                    print(f"{p.name}: дубликат {c['case_id']}"); ok = False
                ids.add(c["case_id"])
                if c["email"].get("message_id") != c["case_id"]:
                    print(f"{p.name}: {c['case_id']} message_id должен совпадать с case_id"); ok = False
            paths = {c.get("path") for c in data}
            print(f"{p.name}: {len(data)} писем, путей: {len(paths)}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
