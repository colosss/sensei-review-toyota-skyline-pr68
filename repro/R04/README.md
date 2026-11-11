# R04: Передайте group_ids по имени при завершении защиты

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. В очередь одной лабораторной и одной пары запишите Alice, затем Bob: места 1 и 2.
2. Администратором выполните `POST /admin/courses/<course>/groups/G1/labs/1/queue/set-status` с телом `{"identifier":"Alice Synthetic","status":"сдал"}`.
3. Запрос возвращает 200, Alice получает результат, но у Bob остаётся место 2. Это видно в листе и `/queue/status`.
4. Ожидается место 1. При добавлении следующего студента текущая реализация способна присвоить ему тоже место 2.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R04/test_R04.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Bob получает место 1; новая Carol — место 2.

Фактический результат на SHA: После завершения Alice и записи Carol оба ожидающих получают место 2: [2, 2] вместо [1, 2].

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R04/run.log). Exit code **1** — ожидаемое падение на дефекте.
