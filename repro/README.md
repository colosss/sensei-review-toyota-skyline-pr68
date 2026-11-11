# Воспроизведения

Для каждой находки выделен каталог `<ID>/` с README и отдельным тестом либо ручным сценарием. Общий изолированный стенд — `conftest.py`, положительные контрольные сценарии — `controls/`.

Перед запуском из корня репозитория:

```bash
git submodule update --init --recursive
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest "$PWD/repro" -q -s -p no:cacheprovider
```

На закреплённой версии ожидается **9 failed, 9 passed**, exit code 1: восемь дефектов R01–R07 и R09; R05 проверяется двумя параметрами. Девять контрольных проверок должны проходить. R10–R12 — ручные сценарии; R08 исключён как неоднозначный и описан в CANDIDATES.md.

Для одной находки используйте `repro/<ID>/test_repro.py`, для контроля — `repro/controls/test_controls.py`. Все переменные приложения задаются тестовыми значениями в conftest.py; настоящие ключи не нужны. Логи временные, YAML использует pytest tmp_path, данные Sheets/GitHub синтетические. Исходники приложения не изменяются.

Поддержан REVIEW_SOURCE с абсолютным путём другого чистого checkout того же закреплённого SHA с инициализированным парсером. Его чистоту и SHA проверьте отдельно; путь указывается в evidence/<ID>/result.json для выполненных запусков.
