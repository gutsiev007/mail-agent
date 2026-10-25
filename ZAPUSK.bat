@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo ============================================
echo   Почтовый агент: полный прогон для сдачи
echo ============================================
python --version >nul 2>&1 || (echo Python не найден. Установи с python.org, галочка "Add to PATH". & pause & exit /b)

echo.
echo [1/5] Проверка стенда...
python -m unittest discover -s tests || (echo Тесты не прошли - пришли скрин. & pause & exit /b)

if "%OPENROUTER_API_KEY%"=="" set /p OPENROUTER_API_KEY=Вставь ключ OpenRouter (sk-or-...) и нажми Enter: 
set CFG=config/models.openrouter.json

echo.
echo [2/5] Пробное письмо...
python -m mailagent run --mode both --cases mail-02 --config %CFG% --batch try-%RANDOM% || (echo Ошибка - пришли скрин. & pause & exit /b)

echo.
echo [3/5] Все письма разработки, промпт p1 (около 15-25 минут)...
python -m mailagent run --mode both --set dev --trials 3 --prompt p1 --config %CFG% --batch dev-p1

echo.
echo [4/5] Исправленный промпт p2 и сравнение...
python -m mailagent run --mode agent --set dev --trials 3 --prompt p2 --config %CFG% --batch dev-p2
python -m mailagent compare dev-p1 dev-p2 --mode agent

echo.
echo [5/5] Новые проверочные письма...
python -c "import json,sys; sys.exit(0 if len(json.load(open('cases/new.json',encoding='utf-8')))>=4 else 1)" && (
  python -m mailagent validate
  python -m mailagent run --mode both --set new --trials 3 --prompt p2 --config %CFG% --batch new-final
) || echo ПРОПУЩЕНО: в cases\new.json меньше 4 писем. Сделай шаг "новые письма" и запусти ЗАПУСК.bat ещё раз.

echo.
echo ГОТОВО. Пришли Claude файлы:
echo   runs\dev-p1\report.md
echo   runs\dev-p2\report.md
echo   runs\compare_dev-p1_vs_dev-p2.md
echo   runs\new-final\report.md  (если есть)
pause
