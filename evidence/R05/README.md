# Доказательства R05

SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Окружение: Python 3.14.8; зависимости source/requirements-dev.txt; точные версии — evidence/baseline/python-dependencies.txt. Fake Sheets и GitHub, настоящие маршруты, grading и YAML. Системное время не меняется.

Команда из корня репозитория:

```text
REVIEW_SOURCE="$PWD/source" .venv/bin/python -m pytest repro/R05/test_R05.py -q -s -p no:cacheprovider
```

Локально команда повторена с REVIEW_SOURCE, указывающим на отдельный чистый checkout того же SHA; в текущем рабочем репозитории source ещё не инициализирован. Точный checkout в result.json. run.log — очищенный вывод, exit code 1.
