# C02 — уникальность активной записи в очередь (discovery)

- Actor: `deepseek-c02-A`
- SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d` (submodule `source/vendor/suai-schedule-parser`: `6ee99733d766ab6f746403996a7a4bef28d6443c`)
- Статус: **refuted** — заявленный инвариант в закреплённом коде выполняется, дефект не обнаружен.
- Receipt: `scratch/pipeline/C02/runs/42e008dfd5964ed2af81d5c06722868e.json`
- Артефакт: `repro/C02/test_c02_active_registration.py` (sha256 `28bdf06b3ce67c29fac8c8b17588fe6e5da394eaa29704f030149f15b29742fd`)

## Требование

Активная (ожидающая) запись в дневной очереди уникальна для одной идентичности
студента в рамках группы, лабораторной и дня. Повторная запись не должна добавлять
вторую строку, а должна возвращать `ALREADY_IN_QUEUE`.

Первичные основания:

- `source/grading/queue/store.py:413-424` — проверка дубля перед `append_row`:
  совпадение `group`, `lab`, `fio` и `status == "ждёт"`; комментарий прямо
  фиксирует, что `session_no` намеренно игнорируется («cannot be waiting twice
  for the same lab on the same day, even across sessions»).
- `source/docs/hackathon/ADR-queue-storage.md:9-12` — очередь живёт один учебный
  день, студент записывается на занятии.
- `source/docs/hackathon/ADR-queue-storage.md:152-154` — два одновременных
  запроса сериализуются мьютексом `sheet_lock(spreadsheet_id)`.

Отдельного требования запрещать ожидание по двум **разным** ЛР в один день нет;
такой случай только наблюдается, чтобы проверить отсутствие лишней блокировки.

## Ожидаемое и фактическое

| Проверка | Ожидание | Факт |
|---|---|---|
| Повтор same identity/group/lab/day | `QueueError(ALREADY_IN_QUEUE)`, одна строка | Так и происходит |
| Повтор в другой паре того же ЛР (`session_no=2` после `1`) | Заблокирован, одна строка с парой 1 | Так и происходит |
| Две разные ЛР у одного студента | Обе записи разрешены (нет требования обратного) | Обе строки, позиция 1 в каждой ЛР |
| Тот же студент на следующий день | Новый лист дня, коллизии нет | Обе записи успешны, по строке на дне |
| Два одновременных одинаковых запроса (barrier, 2 потока) | Ровно один успех и один `ALREADY_IN_QUEUE`, одна строка | Так и происходит |

## Воспроизведение

Из корня рабочего репозитория, только через штатный runner (сеть блокируется,
runtime проверяется по манифесту):

```bash
.venv/bin/python scripts/run_review_tests.py repro/C02/ -v --tb=short
```

Записанный прогон (recorder дополнительно проверяет baseline до и после):

```bash
python3 scripts/review_pipeline.py run C02 --actor deepseek-c02-A --timeout 120 \
  --artifact repro/C02/test_c02_active_registration.py -- \
  .venv/bin/python scripts/run_review_tests.py repro/C02/ -v --tb=short
```

Реальный результат: exit code **0**, `5 passed in 0.62s`, `timed_out=false`,
`baseline_clean_after=true`. Для статуса `refuted` код 0 означает, что
проверяемый контракт выполнен; это не «падающий регрессионный тест».

```
repro/C02/test_c02_active_registration.py::test_second_registration_same_identity_group_lab_day_is_rejected PASSED
repro/C02/test_c02_active_registration.py::test_second_registration_in_other_session_of_same_lab_is_rejected PASSED
repro/C02/test_c02_active_registration.py::test_different_labs_for_same_identity_are_not_blocked PASSED
repro/C02/test_c02_active_registration.py::test_same_identity_on_another_day_has_its_own_tab_and_is_allowed PASSED
repro/C02/test_c02_active_registration.py::test_concurrent_duplicate_registrations_leave_exactly_one_waiting_row PASSED
```

Сырой лог: `scratch/pipeline/C02/runs/42e008dfd5964ed2af81d5c06722868e.log`.
Тест изолирован: fake `Spreadsheet`/`Worksheet` в памяти с id `review-c02-sheet`,
function-scoped фикстуры, `reset_locks()` до и после каждого теста, синтетические
ФИО/группа/ЛР/дата, никаких сетевых вызовов и записи в runtime/YAML.

## Отношение к базе

`base_commit` из `REVIEW_SCOPE.json` — `eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39`.
В базовом коммите файла `grading/queue/store.py` нет:

```bash
git -C source show eef98bb:grading/queue/store.py   # fatal: path ... not in 'eef98bb'
git -C source diff eef98bb..20bea22 -- grading/queue/store.py  # new file mode
```

Значит вся очередь, включая проверку дубля, относится к изменениям PR
(`introduced`). Проверка дубля дополнительно появилась внутри ветки PR
коммитом `7fde5dc "fix double queueing"`. Поведение на базе не запускалось:
в базе нет самого функционала.

## Ограничения

- Проверен слой `grading.queue.store.register`; резолвинг идентичности
  (`main.py:3255-3272`), CI-проверка и HTTP-обёртка замоканы/не исполнялись.
- Идентичность сравнивается как точная строка `fio` (для командных ЛР —
  `team_result.title`); нормализация регистра/пробелов и коллизии одинаковых ФИО
  не исследовались.
- Конкурентность проверена потоками в одном процессе. Межпроцессный сценарий не
  проверялся: ADR прямо ограничивает решение `--workers 1`, внешнего lock нет.
- Случай двух разных ЛР — наблюдение, а не требование; запрет на несколько ЛР не
  подразумевается.
- Реальные Google Sheets/GitHub, HTTP и браузер не использовались.
