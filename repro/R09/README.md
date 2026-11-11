# R09: Отдавайте очередь в порядке актуальных мест после сдвига

SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Синтетические данные: курс review, группа G1, студенты Alice/Bob/Carol Synthetic, лабораторные L1/L2. Условия конкретной находки:

1. В одной лабораторной запишите Alice, затем Bob.
2. Alice выполняет `POST /courses/<course>/groups/G1/labs/1/queue/shift` с `{"delta":1}`. Ответ 200, позиции изменены корректно.
3. Запросите `/queue` или обновите список в интерфейсе.
4. Ответ по-прежнему начинается с Alice (место 2), далее Bob (место 1). Ожидается обратный порядок. В административном `/queue/today` та же проблема.

Из корня репозитория после загрузки закреплённых подмодулей:

```bash
python3 scripts/verify_baseline.py
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements-dev.txt
```

Значения ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY, GITHUB_TOKEN задаёт общий `repro/conftest.py`, только тестовыми строками. Настоящие credentials не нужны. При необходимости можно указать `REVIEW_SOURCE` как абсолютный путь другого чистого checkout того же SHA с тем же парсером.

## Запуск

```bash
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R09/test_R09.py -q -s -p no:cacheprovider
```

Ожидается по требованиям: Список и интерфейс отображают Bob выше Alice согласно новым местам.

Фактический результат на SHA: После сдвига Alice вниз API отдаёт Alice(position=2), Bob(position=1) в прежнем порядке строк; оба веб-списка отображают Alice выше Bob.

Падающий assertion и HTTP-ответы: [run.log](../../evidence/R09/run.log). Exit code **1** — ожидаемое падение на дефекте.
