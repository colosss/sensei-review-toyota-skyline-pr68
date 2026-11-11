# R02: Не изменяйте ячейки оценок при записи в очередь

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. У зарегистрированного студента в тестовой таблице поставьте в существующей колонке L1 значение `?`. Текущий CI репозитория зелёный.
2. Откройте запись по расписанию и отправьте только `POST /courses/<course>/groups/G1/labs/1/queue/register`, без запроса `/grade`.
3. Фактически ответ 200, а ячейка с оценкой меняется с `?` на `v`. При проваленном CI эта же ветка записывает `x`.
4. Ожидается, что операция очереди оставляет колонку оценок без изменений; `?` само по себе не удовлетворяет условию допуска.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R02/test_R02.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Ячейка остаётся ?, запись в очередь отклоняется до самостоятельной успешной проверки работы в сервисе.

Фактический результат на SHA: При POST /queue/register существующая ячейка ? заменяется на v; зафиксирован вызов update_cell(3, 4, 'v').

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R02/run.log). Exit code **1** — ожидаемое падение на дефекте.
