# Матрица контрактов очереди — PR #68

SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`, база `eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39`. Это проверенные локальные контракты авторов, не полное первичное ТЗ заказчика. Freeze не подтверждён. Не используем CANDIDATES.md/docs/rewiev.md как требования.

| Контракт / первичный локальный источник | Проверка | Результат и граница |
|---|---|---|
| Authenticated student withdraw/shift: main.py:3328,3376; identity lookup sheets_context.py:60-77 | C04 clean anonymous/public registration→target mutation; Q03 valid own B+same FIO; API и C04 browser | C04 P1 и Q03 P2. ADR:23-28 НЕ содержит буквальной фразы «только свои» для записи; контракт выведен из authenticated-student операций и раздельного roster identity |
| Group/lab student-route, main.py:3416-3419; student UI title/position QueueSection.jsx:318-353; scoped status main.py:3101,3169 | Разные ЛР/группы, screenshot chain, сравнение API/UI/storage | C06 P2:2из2+3rows2/1/1. Admin QueueViewDialog:32-37 намеренно all-day и использует тот же endpoint — fix должен разделить потребителей |
| Register response/status согласованы по области занятия: main.py:3277,3310,3318 vs3101,3169; дневной sheet ADR:9-22 | Два активных слота одного дня, разные студенты той же группы/ЛР | Q01 P2:1из1 на register и1из2 на status, positions1/1. Не навязывается единственная дневная/парная модель, требуется её согласованность |
| Store set_status явно renumbers: store.py:507-543,384-397; API main.py:3529-3531 | Два студента, admin marks first сдал, status второго | Q02 P2:group_ids попадает в session_no, position2of1 |
| Successful Join вызывает актуальный reload: QueueSection.jsx:125-140; reload80-96; controls241-268 | Реальный browser, unchanged old GET delivered after post-join reads, storage и recovery | C05 P2:notice есть/строки нет, Refresh восстанавливает; конкретный race, не TTL/SLA внешнего сервиса |
| CI non-pass must fail: queue/ci.py:41-54; own tests/test_ci.py:70-87 | Real producer chain+fake GitHub responses success/failure/pending for fixed SHA | C03 P1:real passed string truthy; completed failure200 waiting. Измеренные8GET/attempt не самостоятельный performance defect |
| Частичная отмена lab в slot: docs/schedule-config.md:271-293; CorrectionsDialog:224-229 | Tmp YAML slot without labs, remove_slots slot_id+labs, fake clock+real gate | S01 P2:отменённая ЛР допускается. UI slot_id key, documentation id mismatch отдельно candidate |
| Удалить архивируемый лист только если не изменился: docs/SETUP.md:97-105,129-130; teacher manual edits ADR:110-113 | Fake внешняя правка после read до atomic batch,2regressions | D01 P2:late row/status потеряны. Невозможный partial-batch control исключён; reread не CAS и полный fix не гарантируется |
| Same student/group/lab/day не ожидает дважды, включая разные пары: store.py:413-424 | C02 store sequential+barrier; C08 real HTTP repeat; разных ЛР browser | Exact same lab duplicate409, different labs allowed. Запрет нескольких ЛР не найден; overall C02 не объявляется refuted, visual issue в C06 |
| Преподаватель работает с Sheets напрямую: ADR-queue-storage.md:106-113; QueueViewDialog:32-37 read-only | Чтение контракта, harness admin API selftest | C07 кнопки не обязательны по найденному контракту; admin API bug Q02 отдельно. Full admin browser/deployment не покрыт |
| Shift down positive int, clamp: store.py:481-504; request model main.py:3026-3027 | 0,-1,1.5,1,1000,end; разные identity | C08 matrix8passed, арифметический дефект не найден; wrong target при same FIO отдельно Q03 |
| Process-local locks and persistent Sheets: ADR:75-81,115-117,144-154; команды CLAUDE:139-147 | T01 resolver/cache/locks/store8controls; C02 concurrency; D01 archival | T01 narrow matrix pass, не full team HTTP audit или реальный reboot. Single-worker limitation не дефект |
| Документированный dev/start workflow docs/DEVELOPMENT.md:141-182 | B01 tests/build/lint, C01 config/base compare, disclosed browser stand |973backend/17frontendpass,build0,lint96errors/2warnings. Port mismatch inherited; отсутствие proxy само по себе не дефект student absolute URL+CORS |

## Пробелы

Первичное внешнее задание, актуальное первичное описание PR/ответы команды и официальная фиксация заново не получены. Нельзя утверждать «заказчик требовал управление из admin UI» или «запрещены две разные ЛР» без источника. Прямые комментарии кода о выборе публичной формы вместо OAuth не доказывают безопасность, но и не позволяют объявлять обязательным конкретный OAuth метод.

Реальные Google/GitHub/GUAP, production latency, межсистемные races, stock Docker/browser deployment, полный team HTTP UX, весь schedule editor и reboot не покрыты. База сравнивалась статически, не исполнялась. Каждый findings-файл указывает конкретный контракт, предусловия, шаги, факт и ограничения; успешные controls не доказывают отсутствие дефектов всей области.
