#!/bin/bash
# Прогон после исправлений (инструменты t2, workflow v2). Нужна запущенная Ollama.
cd "$(dirname "$0")"
curl -s http://localhost:11434 >/dev/null || { echo "Ollama не запущена: open -a Ollama"; exit 1; }
c=config/models.local.json
python3 -m mailagent run --mode both --set dev --trials 3 --prompt p2 --config $c --batch dev-v2
python3 -m mailagent run --mode both --set new --trials 3 --prompt p2 --config $c --batch new-v2
python3 -m mailagent compare dev-p2 dev-v2 --mode agent
python3 -m mailagent compare new-final new-v2 --mode agent
python3 -m mailagent compare new-final new-v2 --mode workflow
zip -qr results2.zip runs
echo "ГОТОВО: пришли results2.zip"
open .
