"""CLI:
  python -m mailagent run --mode both --set dev --trials 1 --config config/models.json --prompt p1 --batch dev-p1
  python -m mailagent show <run_id>            # все события одной попытки
  python -m mailagent effects <run_id>         # что реально сделано на стенде
  python -m mailagent report <batch>           # таблица по письмам и метрики
  python -m mailagent compare <batchA> <batchB> --mode agent
  python -m mailagent validate                 # проверить файлы кейсов
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .report import build_report, compare
from .runner import ROOT, load_cases, run_batch
from .trace import format_event, load_run

RUNS = ROOT / "runs"


def _find_batch(run_id: str) -> Path:
    for d in sorted(RUNS.iterdir()) if RUNS.exists() else []:
        if run_id.startswith(d.name + "-") and (d / "trace.jsonl").exists():
            return d
    raise SystemExit(f"Не найден запуск для {run_id}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mailagent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--mode", choices=["agent", "workflow", "both"], default="both")
    r.add_argument("--set", default="dev", help="dev | new | dev,new")
    r.add_argument("--cases", default="", help="через запятую: mail-02,mail-07")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--config", default="config/models.json")
    r.add_argument("--prompt", default="p1")
    r.add_argument("--batch", required=True)
    s = sub.add_parser("show"); s.add_argument("run_id")
    e = sub.add_parser("effects"); e.add_argument("run_id")
    rp = sub.add_parser("report"); rp.add_argument("batch")
    c = sub.add_parser("compare"); c.add_argument("a"); c.add_argument("b"); c.add_argument("--mode", default="agent")
    sub.add_parser("validate")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        cfg = json.loads((ROOT / a.config).read_text(encoding="utf-8"))
        cases = load_cases(a.set.split(","), [x for x in a.cases.split(",") if x])
        modes = ["workflow", "agent"] if a.mode == "both" else [a.mode]
        from .llm import LLMError, make_llm
        try:  # проверить ключи до запуска, чтобы не получить батч из одних ошибок
            for role in {"agent" if m == "agent" else "extractor" for m in modes}:
                make_llm(cfg[role])
        except LLMError as err:
            raise SystemExit(f"Модель не настроена: {err}. См. раздел «Запуск» в README.")
        if (RUNS / a.batch / "results.jsonl").exists():
            raise SystemExit(f"Запуск {a.batch} уже есть — выбери другое имя (старые попытки не перезаписываются)")
        batch_dir, _ = run_batch(cases, modes, a.trials, cfg, a.prompt, a.batch)
        all_cases = {c["case_id"]: c for c in load_cases([p.stem for p in (ROOT / "cases").glob("*.json")])}
        rep = build_report(batch_dir, all_cases)
        (batch_dir / "report.md").write_text(rep, encoding="utf-8")
        print(f"\nОтчёт: {batch_dir / 'report.md'}")
    elif a.cmd == "show":
        for ev in load_run(_find_batch(a.run_id) / "trace.jsonl", a.run_id):
            print(format_event(ev))
    elif a.cmd == "effects":
        st = _find_batch(a.run_id) / "state" / f"{a.run_id}.json"
        print(st.read_text(encoding="utf-8"))
    elif a.cmd == "report":
        all_cases = {c["case_id"]: c for c in load_cases([p.stem for p in (ROOT / "cases").glob("*.json")])}
        print(build_report(RUNS / a.batch, all_cases))
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
            print(f"{p.name}: {len(data)} писем, путей: {len(paths)} ({', '.join(sorted(x for x in paths if x))})")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
