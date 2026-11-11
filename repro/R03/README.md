# R03: Ограничьте студента одной активной записью независимо от лабораторной

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. Настройте открытую пару, разрешающую L1 и L2. У одного студента обе работы имеют `v`.
2. Одной и той же сессией студента выполните `POST /courses/<course>/groups/G1/labs/1/queue/register`.
3. Не выходя из очереди и не отмечая результат, выполните такой же запрос для `/labs/2/queue/register`.
4. Фактически оба ответа 200, в дневном листе две строки этого студента со статусом `ждёт`. Второй запрос должен быть отклонён (в тесте ожидается 409).

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R03/test_R03.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Второй запрос отклоняется, пока первая запись активна.

Фактический результат на SHA: Два последовательных POST register для L1 и L2 от одного студента оба возвращают 200; остаются две ожидающие записи с position=1.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R03/run.log). Exit code **1** — ожидаемое падение на дефекте.
