# R07: Используйте выбранный модуль расписания вместо безусловного ManualScheduleSource

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. Реализуйте минимальный `ScheduleSource` с `list_sessions`, зарегистрируйте его через существующий `register_source('review_university')`; импорт модуля уже выполнен.
2. Создайте YAML: `course-id: review`, `source: review_university`, `groups: {G1: {group_id: G1, slots: []}}`.
3. Выполните `sources = parse_course_schedule('review', <directory>)`, затем `list(sources['G1'].list_sessions(...))`.
4. Фактически тип источника — `ManualScheduleSource`, пользовательский модуль не вызывается. Регистрация в реестре и выбор через YAML не обеспечивают подключение.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R07/test_R07.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Источник, указанный в конфигурации, обрабатывается зарегистрированным модулем.

Фактический результат на SHA: Зарегистрирован source review_university и выбран в YAML, но фабрика возвращает ManualScheduleSource; конструктор и list_sessions выбранного модуля ни разу не вызваны.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R07/run.log). Exit code **1** — ожидаемое падение на дефекте.
