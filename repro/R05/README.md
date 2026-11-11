# R05: Сохраняйте видимость ожидающих после закрытия записи по расписанию

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. В тестовом расписании пара 09.11.2026 10:40–12:10, `auto_close_minutes_after: 0`.
2. В 11:00 студент записывается и получает место 1.
3. В 12:11 обновляет свою страницу либо запрашивает `/queue/status` и `/queue`.
4. Фактически личная запись исчезает из обоих ответов. В листе она всё ещё `ждёт`; новые POST корректно запрещены с 403.
5. Ожидается сохранение личного места и списка до конца дня. В интерфейсе из-за ложного `in_queue=false` также исчезает кнопка выхода.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R05/test_R05.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: queue_open=false и запрет новых записей, но in_queue=true и прежнее место у уже ожидающего; очередь доступна для просмотра.

Фактический результат на SHA: Через минуту после закрытия окна /queue/status сообщает in_queue=false, position=null, queue_size=0, а /queue возвращает пустой список, хотя строка ждёт остаётся в хранилище.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R05/run.log). Exit code **1** — ожидаемое падение на дефекте.
