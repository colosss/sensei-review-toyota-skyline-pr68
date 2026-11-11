# R06: Предусмотрите дневную очередь для курса без расписания

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. На тестовом курсе с группой и прошедшей проверку L1 не создавайте `schedules/<course>.yaml`.
2. В течение дня заполните анкету и откройте очередь.
3. `/queue/status` возвращает `queue_open:false`; `POST /courses/<course>/groups/G1/labs/1/queue/register` даёт `403 {"detail":"QUEUE_CLOSED"}`.
4. Ожидается доступная дневная очередь согласно отдельно оговорённому режиму без расписания.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R06/test_R06.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: В режиме без расписания студент может записаться в дневную очередь.

Фактический результат на SHA: Без schedules/review.yaml GET status всегда queue_open=false, POST register отвечает 403 QUEUE_CLOSED даже днём и при проверенной работе.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R06/run.log). Exit code **1** — ожидаемое падение на дефекте.
