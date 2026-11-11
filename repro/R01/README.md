# R01: Не считайте строку с числом пройденных CI-тестов успешным результатом

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. На тестовом курсе настройте обычную индивидуальную L1, группу G1 и существующего в таблице студента; в ячейке L1 стоит `x`.
2. В репозитории студента один завершённый check-run с `conclusion: failure`; обязательные файлы и остальные проверки репозитория корректны.
3. Заполните обычную анкету студента, чтобы получить `student_session`. Во время открытой пары отправьте `POST /courses/<course>/groups/G1/labs/1/queue/register`.
4. Фактически ответ `200 {"position":1,"queue_size":1}`; студент появился в дневном листе несмотря на провал CI.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R01/test_R01.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Запись отклонена, ожидающих записей не добавлено.

Фактический результат на SHA: POST /queue/register возвращает HTTP 200 и position=1 при текущей оценке x и завершившемся CI с conclusion=failure; проверка дала 0/1 тестов пройдено.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R01/run.log). Exit code **1** — ожидаемое падение на дефекте.
