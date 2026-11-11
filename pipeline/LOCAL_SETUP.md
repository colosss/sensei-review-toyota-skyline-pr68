# Локальная настройка ревью

Настройка выполнена 11.11.2026 по поручению пользователя. Исходники и SHA не изменены. Это состояние инструментов, не результат поиска дефектов.

## Zed

В пользовательский `~/.config/zed/settings.json` добавлен профиль **Review PR68 · Sol + DeepSeek** (`review-pr68`):

- координатор: `openai-subscribed / gpt-6.1-sol`, high;
- подагенты: `cheapvibecode / deepseek-v4.1-flash-1017`, medium;
- инструменты чтения/терминала/делегирования из существующего профиля Deep;
- доступ к context servers.

Глобальный `agent.subagent_model` переключён с Opus на DeepSeek. Это влияет на подагентов встроенного Zed Agent и в других профилях. Основная модель по умолчанию и существующие Deep/Fast/Ask сохранены. Новый профиль нужно выбрать в новом native Zed Agent thread; текущий Codex ACP не превращается в native Zed Agent автоматически.

Добавлен MCP **review-playwright**: `npx -y @playwright/mcp@0.0.85 --browser=chrome --isolated --caps=vision,devtools`. Версия сверена с npm; STDIO initialize, tools/list, навигация на локальный сайт и snapshot реально проверены (44 инструмента). Созданный тестовый браузер закрыт.

Перед правкой создана резервная копия настроек в `~/.config/zed/backups/settings.before-review-pr68-20261111-150414.json`. Для отката восстанови именно эту копию, предварительно сохранив более поздние изменения. Не заменяй весь файл настроек примером из документации.

## Авторизация и пробный DeepSeek

Ключ CheapVibeCode найден в локальном Secret Service по URL уже настроенного провайдера. Значение не выводилось, не сохранялось в репозиторий и не передавалось модели. Скрипт `scripts/smoke_review_worker.py` читает только этот credential и выполняет максимум четыре API-запроса с ограничением вывода; повторный запуск расходует API-квоту.

Выполнен один smoke из трёх API-запросов: модель вызвала read_fixture → run_check → write_result, локальная проверка и итоговый nonce/сумма прошли. Передан ID `deepseek-v4.1-flash-1017`; сервер вернул имя `deepseek-v4.1-flash`. Это подтверждает работу запроса и tool calling, но не устанавливает внутреннюю версию модели у агрегатора. В сумме в ответах указано 1819 total tokens по трём запросам; стоимость в деньгах не проверялась.

Это прямой ограниченный tool harness, **не** подтверждение делегирования внутри Zed. Результаты без ключей: `scratch/setup-smoke/summary.json` и `worker-result.json`.

При первоначальной настройке credential ChatGPT Subscription для native Zed отсутствовал. После сообщения пользователя «готово» его наличие в Secret Service подтверждено; значения токенов не читались. Пользователь затем предоставил скриншот native Zed: создан один DeepSeek-подагент, команда дала stdout 42 и exit 0. Сохранённый zed-worker-result.json независимо сопоставлен с fixture: nonce, сумма и exit code совпадают. На скриншоте указано, что файл уже существовал: его содержимое само по себе не доказывает свежесть выполнения; подтверждение запуска опирается на отображённый отчёт Zed. Отдельная авторизация Codex уже есть, но она не переносилась в Zed. Пользователю отправлена просьба выполнить штатный **Agent → Configure → LLM Providers → ChatGPT Subscription → Sign in**. Вход и наличие Sol в каталоге native-провайдера нужно подтвердить в Zed. [Порядок входа у Zed](https://zed.dev/blog/chatgpt-subscription-in-zed).

## Python и изолированный запуск

Создана `.venv` на Python 3.12.13; установлены `source/requirements-dev.txt` и дополнительный SecretStorage для credential-backed smoke. Снимок установленных версий: `scratch/setup-smoke/requirements-frozen.txt`. Непинованные зависимости проекта устанавливались без изменения source requirements.

Подготовлена отдельная копия приложения из закреплённых Git-архивов, включая вложенный подмодуль: `scratch/runtime/app`. Она не использует код или окружение sensei-mcp. Manifest SHA и хэши файлов хранятся рядом; wrapper проверяет исходный baseline и сохранённые файлы runtime перед тестом.

```bash
.venv/bin/python scripts/prepare_review_runtime.py
.venv/bin/python scripts/run_review_tests.py source/tests/test_session.py -q
.venv/bin/python scripts/run_review_tests.py "$PWD/pipeline/smoke/test_isolation.py" -q
```

Запуск существующих двух session-тестов прошёл. Они проверялись как smoke окружения, не как независимый аудит авторизации. Полный набор тестов приложения ещё не запускался.

`run_review_tests.py` использует фиктивные application credentials, отдельный LOG_DIR, отключает pyc/cache в копии приложения и блокирует внешний DNS/TCP на уровне Python socket. Loopback разрешён. Это не OS-песочница: subprocess/native code может обойти guard; для новых сценариев всё равно требуются соответствующие контракту fake-клиенты. Smoke fake-интеграции показывает способ подмены HTTP через responses.

Для записи воспроизведения в пайплайн используй wrapper, например после создания настоящего теста:

```bash
python3 scripts/review_pipeline.py run C02 --actor worker-queue-A \
  --artifact repro/C02/test_unique_registration.py -- \
  .venv/bin/python scripts/run_review_tests.py repro/C02/test_unique_registration.py -q
```

Пример теста C02 ещё не реализован. Browser mutations очереди требуют собственного изолированного backend/Sheets fixture: доступный сейчас сайт и его фиктивные ключи не заменяют такое хранилище. API-проверки можно начинать через имеющиеся тестовые fake-клиенты и TestClient.

## После входа ChatGPT

1. Новый **Zed Agent** thread, профиль **Review PR68 · Sol + DeepSeek**. Проверь в UI провайдер ChatGPT Subscription и Sol 6.1.
2. Попроси координатора создать одного DeepSeek-подагента: прочитать `scratch/setup-smoke/fixture.json`, выполнить `.venv/bin/python -c 'print(13 + 29)'`, сохранить ответ в `scratch/setup-smoke/zed-worker-result.md`. Ничего в source не менять. Проверь фактическую модель в карточке подагента.
3. После успешного native-делегирования передай стартовый запрос из PIPELINE.md. Начинай B01, затем C02/C04. Не обходи непроверенный официальный freeze и не публикуй замечания автоматически.

Шаги входа и native-делегирования нельзя считать выполненными только по наличию JSON-настроек или прямому smoke API.
