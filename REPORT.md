# Ревью очереди toyota-skyline — PR #68

Дата: 11.11.2026. Координатор Sol, встроенный Zed Agent. Область — очередь и добавленные в PR связи с CI/расписанием/идентификацией/архивом; не общий аудит всех функций приложения. **Девять независимо подтверждённых локальных замечаний**, оформлены в findings. GitHub Review не опубликован; официальный freeze не подтверждён, финальный bundle не создавался.

## Объект и безопасность

- PR: https://github.com/markpolyak/lab_grader_web/pull/68
- Source SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`; vendor `6ee99733d766ab6f746403996a7a4bef28d6443c`; база `eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39`.
- Baseline/preflight в начале и baseline после recorder-прогонов чистые. `source/`, vendor и закрепление SHA не менялись. Приложение не исправлялось. Изменения только в материалах ревью вне source.
- Ветка существовавшая `review/agent-coordination`, без переключений и коммитов. Пользовательские изменения PIPELINE.md/setup scripts сохранены. Ничего не публиковалось на GitHub, секреты/реальные персональные данные не использовались.
- `organizer_freeze_verified=false`: первичный источник фиксации сдачи не получен, флаг не менялся. Это не препятствует локальному исследованию выбранного SHA, но не позволяет объявлять набор готовым к зачёту.
- Полное первичное ТЗ заказчика/организатора и первичное описание PR заново не получены. Требования в `REQUIREMENTS.md` — собственные docs/ADR/контракты авторов и наблюдаемая целостность операций; не выдаём жалобы или docs/rewiev.md за внешнее ТЗ. Не найден запрет одновременно ждать разных лабораторных.

## Ответ по восьми наблюдениям коллеги

| Жалоба | Что установлено | Итог |
|---|---|---|
| 1. Нет nginx proxy | Student API использует абсолютный API_BASE_URL и CORS, отсутствие proxy само по себе не ломает этот путь. Stock compose8080:80 против nginx listen8080 действительно рассогласован, но файлы byte-identical базе. Harness делает явный API-base override, не доказывает stock deployment | C01 inherited, нового замечания PR нет |
| 2. Две записи/несколько ЛР | Лично браузером один Иванов записан на ЛР1 и ЛР2; обе строки появляются на экране одной ЛР. Это реальное наблюдение, не опровергнутое unit-тестом. Запрет разных ЛР не установлен; повтор той же exact identity/ЛР отклонён в store и HTTP. Причина скриншота list scope подтверждена | C02 перенаправлен как duplicate C06, а не общее refuted; связанные Q01/Q03 отдельно |
| 3. Неэффективная проверка через Git | Подтверждён более существенный дефект: завершённый красный CI допускает в очередь из-за строкового passed. 8 GitHub GET на попытку и повторные проверки наблюдались, но performance-отказ не доказан; TOCTOU нескольких SHA reads унаследован | C03 accepted P1, performance отдельно не заявляется |
| 4. Можно ввести другого человека | Новая чистая browser-сессия регистрирует точные ФИО+публичный login Петровой, затем кнопкой отзывает её запись. Не просто ввод имени, а фактическая мутация | C04 accepted P1; отдельная FIO collision — Q03 |
| 5. Подтверждение есть, строки нет | Браузером воспроизведено: старый Refresh-ответ, начатый до Join, прибывает после post-join reload и скрывает строку/позицию при success notice. Запись в storage остаётся; Refresh восстанавливает | C05 accepted P2 для response-order race; исходный триггер коллеги и TTL не установлены |
| 6. Номера2/1/1 | HTTP-цепочка даёт в точности2/1/1 при собственном2из2; UI подтверждён и с одним Ивановым на двух ЛР. В выдачу попадают другие ЛР/группы без маркировки. Ещё две независимые причины: scope пары и admin renumber | C06, Q01, Q02 accepted P2, раздельные корни |
| 7. Admin UI без действий | ADR выбирает работу преподавателя напрямую в Sheets; QueueViewDialog явно read-only и сознательно потребляет all-day список. Admin today/set-status/snapshot API существуют; set-status имеет отдельный дефект | C07 refuted только как обязательность кнопок; Q02 accepted |
| 8. Странный сдвиг/два Ивановых | 1 сдвигает,1000 ограничивается концом, в конце400 intentional,0/-1/1.5 отклоняются422. Числового overflow в матрице нет. Но настоящий тёзка с другим валидным login может сдвинуть/отозвать A из-за FIO-key | C08 refuted только арифметика; Q03/C06/Q01 покрывают реальные странности |

Реконструкция скриншота не доказывает конкретные личности/ЛР/действия исходного окружения. В browser fixture Петрова уже стояла первой, поэтому порядок строк1/2/1, но противоречие2из2 и3строк то же; API fixture даёт точный порядок2/1/1. Из двух одинаковых подписей нельзя автоматически заключать две активные записи одного stable ID в одну ЛР.

## Принятые замечания (одна причина — одно замечание)

| ID | Приоритет | Суть | Материал |
|---|---|---|---|
| C04 | P1 | Публичная форма выдаёт queue-authority от чужой личности | findings/C04.md |
| C03 | P1 | Truthy строка passed пропускает failure CI | findings/C03.md |
| C05 | P2 | Старое чтение стирает отображение успешного Join | findings/C05.md |
| C06 | P2 | Student list смешивает group/lab scope, статус ему противоречит | findings/C06.md |
| Q01 | P2 | Register считает по паре, status/мутации — по дню | findings/Q01.md |
| Q02 | P2 | group_ids ошибочно передан как session_no: position2of1 | findings/Q02.md |
| Q03 | P2 | Валидные разные usernames с одинаковым ФИО меняют A | findings/Q03.md |
| S01 | P2 | Частичная отмена labs игнорируется при slot labs:null | findings/S01.md |
| D01 | P2 | Внешняя поздняя правка теряется при архивном deleteSheet | findings/D01.md |

Приоритеты — оценка координатора по воздействию и предусловиям, не официальная классификация организатора. D01 требует внешней правки прошлого дня и узкого окна. Q03 требует тёзок в одной группе. Сопутствующие historical-position дубли после выхода не приняты отдельным дефектом: журнал со статусами может их сохранять. C06 final учитывает, что admin viewer намеренно использует общий endpoint; корректировать student consumer нужно без слома предусмотренного teacher all-day просмотра.

Отделимость: проверка личности C04 не устраняет FIO collision Q03; фильтр group/lab C06 не исправляет одну группу/ЛР с разными парами Q01 и неверный аргумент Q02; C05 — временная гонка UI, не scope; C03 — отдельный guard CI; S01 — отдельный schedule gate; D01 — сохранность архива. Новые неподтверждённые причины в принятые пакеты не добавлялись.

## Как проверяли

### B01 и штатные проверки

Ранее выполнены и сохранены в scratch/pipeline/B01:
- Backend `.venv/bin/python scripts/run_review_tests.py source/tests/ -v --tb=short`:973passed,1StarletteDeprecationWarning, exit0, receipt79f342b968a648e2870575942a7466dc.
- Frontend `npm --prefix scratch/runtime/app/frontend/courses-front test`:17passed, exit0, receipt7e8bf2a4ee7349d7a9e432fde56127d7.
- Production build exit0, receipteaa0cf2dcf704715b09b5804e9083979; предупреждения TabList export/large chunk, runtime impact отдельно не доказан.
- ESLint exit1:96errors/2warnings, receiptac5a03e8919d4c5e9571e757de43993d. Не исправлялся и не выдаётся за9 подтверждённых дефектов. Наследование каждого lint-сообщения не проверялось.
- Первые missing-dependency failures127 и offline npm ENOTCACHED — окружение. Обычный npm ci с --legacy-peer-deps --ignore-scripts --no-audit --no-fund прошёл только в disposable копии, lock/source не менялись.

Python3.12.13, pytest9.2.0, Node24.12.0, npm11.6.2, Docker29.8.1. Версии Python-пакетов через importlib.metadata (pip-модуля нет) в scratch/pipeline/B01/requirements-frozen.txt. Diff карты:64файла,+12512/-128, см. B01/coverage.md,diff-map.txt,main-diff.txt. Повтор полного штатного набора после паузы не делался: приложение не менялось, выполнялись новые целевые проверки.

### Изоляция и практическая проверка

- Pinned приложение экспортировано в scratch/runtime/app; wrapper проверяет baseline и file manifest, ставит только synthetic credentials, блокирует внешние Python socket/DNS. Это НЕ OS sandbox, loopback разрешён; native/subprocess могут обойти guard.
- Все pytest-прогоны только через scripts/run_review_tests.py. Независимые пакеты — отдельные процессы, fresh in-memory fake Sheets, разные synthetic IDs, tmp_path для YAML. Общий LOG_DIR только диагностический, не state/evidence; доказательства по раздельным recorder logs и состояниям фикстур.
- Настоящий построенный frontend и real FastAPI/store/auth запущены в отдельном loopback browser harness repro/C01/harness,18280/18281. В served JS bytes только API base localhost8000→127.0.0.1:18280, файлы dist не менялись. Sheets/GitHub/CI/active schedule synthetic; никаких production интеграций.
- Sol прошёл course→group→lab→form→join→другаяЛР→shift и отдельную сессию чужого withdraw; saved screenshot evidence/C06 и evidence/C04. C05 personally повторен до/после паузы и независимо DeepSeek: реальный GET задержан, bytes не подменены, stale/current/storage/recovery сверены.
- Browser сценарии классифицированы как наблюдения с manual_observation/observed_steps, не как зелёные regression. Ручной воспроизводимый сценарий допустим без pytest-receipt.

### Независимость и модель

Native delegation smoke пройден ранее (fixture/command42/nonce/result independently checked). Model ID явно выбран cheapvibecode/deepseek-v4.1-flash-1017. Первая волна2исполнителя, после приёмки3в параллельных независимых областях. Авторы переназначались проверяющими ЧУЖИХ пакетов. Общие документы/decisions/findings — Sol. Внутренний backend агрегатора не аттестован; стоимость/token usage native tools не предоставили. Пользователь запросил максимальное мышление, но spawn_agent не имеет reasoning-effort параметра: принудительное max не подтверждено, глобальные настройки не менялись.

## Последние собственные прогоны координатора

Каждая команда обёрнута recorder `review_pipeline.py run <ID> --actor sol-final-audit --timeout120 --artifact ... -- .venv/bin/python scripts/run_review_tests.py <target> -v --tb=short`; существенные external helpers и wrapper хэшированы. Все baseline_clean_after=true,timed_out=false. Хэши inputs/logs отдельно сверены. Ни одно падение ниже не import/setup/timeout.

| ID | Target | Итог | Receipt в scratch/pipeline/ID/runs/ |
|---|---|---|---|
| C03 | repro/C03/test_ci_admission.py |2failed/2passed,exit1 |fe050714eed64c2eb8b0d84f687c5b18.json |
| S01 | repro/S01/test_schedule_gate.py |1failed/3passed,exit1 |9ef49c9fcfa14e9db1f8deffa04518e2.json |
| C06 | repro/C06/test_c06_screenshot_chain.py |1failed/2passed,exit1 |b358bf19403e417880c2b693ba981b3f.json |
| Q01 | repro/C06/test_c06_session_scope.py |1failed/1passed,exit1 |f1d4fe24fdca49388bb6e9efbacf386e.json |
| Q02 | repro/C06/test_c06_set_status_renumber.py |1failed/1passed,exit1 |8d3658b1c954496f8efc9a812c222570.json |
| Q03 | repro/Q03/test_q03_same_fio_distinct_login.py |2failed/3passed,exit1 |39c56520ab6247fc8234888d7d17855d.json |
| D01 |2 regression nodeids из repro/D01/test_d01_snapshot.py |2failed,exit1 |124cae3f99874b11ab32716c05d4527a.json |
| C08 | repro/C08/test_c08_shift_matrix.py |8passed,exit0 |e900d3eec5864cb79138750acf555dab.json |
| T01 | repro/T01/test_t01_teams_isolation.py |8passed,exit0 |5f1f8fde3a99498281adb50224d98aa7.json |

C04 ранее Sol5ac6164330c64f7db265bd0533a7349c:2failed/1passed,exit1, плюс independent verifier. C05 — real browser file repro/C05/browser_stale_reload.js, наблюдение без recorder, independent evidence/C05/verification-browser.txt и verification-stale.png. В findings каждого пакета приведены авторские, independent и Sol запуски и фактические failing assertions.

`review_pipeline.py check` для C03,C04,C05,C06,Q01,Q02,Q03,S01,D01 завершился0 (Packet complete). Это проверка комплектности и hashes, НЕ автоматическое доказательство смысла. Sol принял после чтения кода/контрактов/базы/тестов/результатов и собственного повтора. Черновики агентов DRAFT_REVIEW и предыдущие raw discoveries не заменяют final REVIEW/findings.

## Честные ограничения и исключённые доказательства

- D01 full author suite имел control append-success/delete-failure внутри одного атомарного Sheets batch. Такой partial batch невозможен по использованному контракту; контроль исключён из доказательства реального отказа. Старые receipt/input не переписаны. Sol отдельно запустил только late-write regressions без fail_mode, которые не зависят от partial batch. См. evidence/D01/contract-caveats.txt. Re-read не CAS; абсолютная гарантия фикса не обещается.
- Q03 синтетически подписанная собственная сессия моделирует корректно удостоверенную личность B; это НЕ реальный OAuth login. Реальный callback в очереди отдельную student_session не доказан и в вывод не включён.
- Реальные Google Sheets/GitHub OAuth/GUAP, квоты, production timing, reboot backend и одновременный backend↔Apps Script не проверены. D01 проверяет supported external-write interleaving через fake, не интеграционную гонку двух живых сервисов.
- S01 только manual-YAML gate, не весь schedule editor/GUAP/parity/refresh. id vs slot_id в документации — extra candidate, не отдельная принятая находка.
- T01 только resolver/store/cache-key/lock модули,8контролей; full HTTP/browser team flow не пройден. Уникальность названий команд установлена для create_team, ручные сторонние repo и group policy — пробелы.
- C02 narrow5tests и C08 HTTP duplicate контроль не доказывают невозможность всех конкурентных повторов. Стартовый barrier+read delay не исчерпывает interleavings. Коллизия stable identity→FIO отдельно Q03. Поведение разных ЛР наблюдалось, нарушенный запрет этого поведения не найден.
- C01 Docker/nginx не запускались; inherited port mismatch установлен конфигом/base. Browser stand с disclosed override не доказывает штатный Compose. Admin UI read-only намеренный; полной browser-проверки admin deployment нет.
- Base comparison для новых функциональностей статическое; исполнения базы не было. Новые ошибки PR отделены от inherited публичной формы и port mismatch.

## Статусы всех пакетов и оставшиеся пробелы

B01 blocked как coverage-пакет (проверки выполнены, внешний freeze/полное ТЗ/stock deployment не закрыты), C01 inherited, C02 duplicate→C06 с оговорками, C03/C04/C05/C06 accepted, C07 refuted узко, C08 refuted узко, Q01/Q02/Q03 accepted, S01/D01 accepted, T01 refuted узко. Refuted здесь не означает отсутствие дефектов во всей области.

Новых находок исключительно «за отсутствие функции заказчика» без первичного требования не создавали. Наличие всех девяти локальных замечаний не доказывает полноту покрытия очереди или готовность к зачёту. Сначала требуется подтвердить официальный freeze, затем человек может выбрать замечания для публикации.

## Процессы и артефакты

Browser стенды запускались с конечным supervisor deadline и ручной остановкой собственных launcher children; состояние только in-memory. После работы собственные backend/static/launcher завершаются и браузер закрывается. Новых контейнеров не создавалось. Предсуществующие toyota-review68-backend-1/frontend-1 (8100/8180) не трогались: backend mounted neighboring checkout, frontend image без verified application SHA, поэтому они не служат pinned доказательством.

Сырые recorder/browser tool логи остаются в scratch; публикуемые evidence — очищенные synthetic summaries/screenshots. Существующие файлы автора с уточняемыми трактовками не переписывались после receipt: финальные REVIEW явно сужают спорные цитаты/направление shift и excluded controls. Финальный baseline, checks, whitespace/secret hygiene и остановка собственных процессов проверяются перед завершением; результаты фиксации выводятся в беседу. Никаких GitHub публикаций, доступа к production, коммитов и исправлений приложения.
