# Отчёт: лабораторные работы 3-4 (X5 Tech, «Веб-разработка на Python»)

| ДЗ | Тема | Каталог |
|---|---|---|
| ДЗ3 | Проектирование API-контрактов | [`library-api/`](library-api/README.md) |
| ДЗ4 | Асинхронность и интеграции | [`async_loader/`](async_loader/) |

## Цель

- **ДЗ3.** Спроектировать OpenAPI 3.1 контракт сервиса «Библиотека» (книги, читатели,
  выдачи) с бизнес-правилами, единым форматом ошибок, пагинацией и политикой
  `Idempotency-Key`, оформить правила API (`STYLE.md`) и саморевью (`REVIEW.md`).
- **ДЗ4.** На сквозном примере асинхронного загрузчика URL показать: почему `await` в
  цикле не даёт ускорения, разницу sync/async, таймауты и ретраи с экспоненциальным
  backoff, вынос CPU-bound-вычислений из event loop.

## Структура файлов

```text
lab3-4/
├── REPORT.md                  # этот отчёт
├── requirements.txt           # зависимости ДЗ4 и инструменты проверки
├── pytest.ini                 # pythonpath = . , testpaths = tests
├── ruff.toml                  # src = ["."] для корректной сортировки импортов
├── library-api/               # ДЗ3
│   ├── openapi.yaml           # контракт OpenAPI 3.1
│   ├── STYLE.md               # 10 правил API
│   ├── REVIEW.md              # саморевью по слайдам 31-35
│   ├── README.md              # операции, правила, бонусы (mock, JWT, deprecated, v2)
│   └── redocly.yaml           # конфиг линтера Redocly
├── async_loader/              # ДЗ4: одно задание - один файл
│   ├── common.py              # общая заготовка: URLS, BROKEN_URLS, timed
│   ├── task0_slow_main.py     # задание 0: ловушка await в цикле
│   ├── task1_sync_vs_async.py # задание 1: requests vs httpx + TaskGroup
│   ├── task2_robust.py        # задание 2: таймаут, backoff, устойчивость
│   └── task3_cpu_bound.py     # задание 3*: ProcessPoolExecutor и ticker
└── tests/
    ├── test_library_contract.py  # 15 тестов контракта
    └── test_async_loader.py      # 12 тестов загрузчика (без сети)
```

## ДЗ3. Контракт «Библиотека»

### Реализация

- `servers` с `/v1`, 14 операций: CRUD для `Books` и `Readers`, для `Loans` - создание,
  список, получение по id и возврат `POST /loans/{loan_id}/return` (`DELETE` нет).
- Request и response разделены: `Book` / `CreateBookRequest` / `UpdateBookRequest` и т.д.
  Серверные поля (`id`, `available_copies`, `registered_at`, `loaned_at`, `returned_at`,
  `status`) - `readOnly` и отсутствуют в request-схемах; все request-схемы
  `additionalProperties: false`.
- Коллекции: фильтры (`author`, `published_year_gte`, `available`, `status`, `reader_id`,
  `due_date_lt`, ...), `sort=<поле>|-<поле>` с enum и default, `limit` (20, максимум 100) + `offset`.
  Просроченные - `GET /loans?status=overdue`.
- Единый `ErrorResponse` (`error.code`, `message`, `details[]`, `request_id`) с кодами
  `INVALID_REQUEST`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`, `BUSINESS_RULE_VIOLATION`,
  `IDEMPOTENCY_MISMATCH` и дополнительным `UNAUTHORIZED` для JWT.
- Все бизнес-правила - ответы `409`/`422` с examples. `Idempotency-Key` (uuid, обязателен)
  на `POST /loans`: полный replay, `422 IDEMPOTENCY_MISMATCH`, `409 CONFLICT` для
  конкурентного повтора, хранение 24 часа.
- Бонус - все 4 пункта: Prism mock + curl (реальный вывод в README), Bearer JWT,
  `deprecated` поле `Loan.is_overdue`, таблица совместимых/несовместимых изменений для v2.

### Принятые решения

| Решение | Почему |
|---|---|
| Бизнес-конфликт - `409`, валидация значений - `422`, неразбираемый запрос/параметр - `400` | Так разделяют коды слайды 25 и 33 |
| `IDEMPOTENCY_MISMATCH` - `422`, конкурентный повтор - `409` + `Retry-After` | Как в черновике IETF Idempotency-Key header |
| Возврат идемпотентен по природе (повтор - `200` с тем же `returned_at`) | Ретрай возврата безопасен без отдельного ключа |
| `PATCH /books` не даёт `total_copies` < числа активных выдач | Иначе `available_copies` стал бы отрицательным |
| offset-пагинация | Небольшие и редко меняющиеся списки, нужен `total` для UI |
| Добавлен код `UNAUTHORIZED` | После бонуса с JWT нужен код для `401`; требуемые 6 кодов сохранены |

## ДЗ4. Асинхронный загрузчик

В начале каждого файла - docstring с объяснением и замерами. Замеры сделаны на
Windows 11, Python 3.14.7, домашний интернет, 25.10.2026, два прогона подряд:

| Задание | Вариант | Прогон 1 | Прогон 2 |
|---|---|---|---|
| 0 | `slow_main` (await в цикле) | 8.73 s | 7.95 s |
| 0 | `fixed_main` (`asyncio.gather`) | 2.83 s | 2.79 s |
| 1 | `sync_main` (requests) | 29.05 s | 47.72 s |
| 1 | `fast_main` (httpx + TaskGroup) | 3.08 s | 2.98 s |
| 2 | `robust_main` (20 URL + 2 битых) | 22.45 s | 22.52 s |
| 3 | sha256 в корутине: время / тиков ticker | 2.28 s / 0 | 1.49 s / 0 |
| 3 | `ProcessPoolExecutor`: время / тиков ticker | 0.37 s / 3 | 0.23 s / 2 |

Выводы:

- **Задание 0.** `await` внутри `for` ждёт каждый запрос до конца, прежде чем начать
  следующий: в loop одна задача, конкурентности нет. `asyncio.gather` запускает все
  запросы сразу. `follow_redirects=True` указан во всех `AsyncClient`.
- **Задание 1.** requests ждёт ответы по очереди, и времена складываются; `AsyncClient` +
  `TaskGroup` держит все 20 запросов в сети одновременно - ускорение в 10-16 раз.
- **Задание 2.** Таймаут 5 s на запрос, 3 попытки с паузами 1 s → 2 s (следующая была бы 4 s),
  повторяются только сетевые ошибки, 429 и 5xx. Каждый URL - своя задача, исключение
  превращается в `FetchError`, поэтому `robust_main` вернул 20 результатов и 2 ошибки
  (`ConnectError` для `no-such-site.invalid`, `ReadTimeout` для `httpbin.org/delay/10`).
- **Задание 3.** Пока sha256 считается прямо в корутине, ticker не напечатал ни одной точки;
  с `run_in_executor` + `ProcessPoolExecutor` точки идут во время вычислений, а хеши
  совпадают с вариантом «в лоб».

### Принятые решения

| Решение | Почему |
|---|---|
| Общая заготовка вынесена в `common.py`, задание 1 переиспользует `fetch` из задания 0 | Нет дублирования, «каждый новый навык ложится на уже написанный код» |
| `robust_fetch` возвращает `FetchResult` (url, статус, размер), а не `int` | Результат самодостаточен в списке результатов; статус по-прежнему доступен |
| Ретраи только для временных сбоев | Повтор `404` бессмыслен и лишь задерживает ответ |
| `sleep` и `client` внедряются параметрами | Тесты проверяют расписание backoff мгновенно и без сети |
| Тики ticker считаются, а не только печатаются | Замирание loop видно числом в выводе и проверяется тестом |

## Команды запуска

```bash
# из корня репозитория
python -m venv .venv
.venv\Scripts\activate            # Windows; Linux/macOS: source .venv/bin/activate
python -m pip install -r lab3-4/requirements.txt

cd lab3-4
python -m async_loader.task0_slow_main
python -m async_loader.task1_sync_vs_async
python -m async_loader.task2_robust
python -m async_loader.task3_cpu_bound

# проверки
python -m pytest
ruff check . && ruff format --check .
openapi-spec-validator library-api/openapi.yaml
cd library-api && npx @redocly/cli lint openapi.yaml
npx @stoplight/prism-cli@5 mock openapi.yaml -p 4010   # mock-сервер
```

В Git Bash на Windows для корректного вывода кириллицы задайте `PYTHONIOENCODING=utf-8`.

## Результаты проверок

Все проверки ниже реально запускались в ветке перед открытием PR:

| Проверка | Результат |
|---|---|
| `python -m pytest` (из `lab3-4/` и из корня) | 27 passed; 3 повторных прогона подряд - стабильно |
| `ruff check` / `ruff format --check` (Ruff 0.17.1) | All checks passed; все файлы отформатированы |
| `openapi-spec-validator library-api/openapi.yaml` | OK |
| `npx @redocly/cli lint openapi.yaml` (recommended) | valid, 0 предупреждений (правило `no-server-example.com` отключено осознанно) |
| Prism mock + curl | 200 / 201 / 409 / 422 / 401 получены, вывод в `library-api/README.md` |
| Запуск всех 4 скриптов ДЗ4 на реальной сети | замеры в таблице выше |
| Мутационная проверка тестов контракта | 5 из 5 внесённых нарушений пойманы |

## Известные ограничения

- Замеры ДЗ4 зависят от сети и нагрузки на picsum.photos/httpbin.org: разброс sync
  (29-48 s) показывает это наглядно. Повторный запуск даст другие числа, но тот же порядок.
- `task2_robust` идёт в реальную сеть, полный прогон занимает около 22 s из-за ретраев
  `httpbin.org/delay/10`; ретраи для DNS-ошибки тоже выполняются, так как httpx не
  отличает их от временных проблем подключения.
- В задании 3 на 16-ядерной машине вариант с пулом длится доли секунды, поэтому точек
  ticker немного (2-3); их число соответствует ожидаемому для этой длительности.
- Prism не хранит состояние: replay по `Idempotency-Key` и бизнес-правила он не исполняет,
  а при отсутствии ключа отвечает `422` вместо описанного в контракте `400`.
- ДЗ3 - только контракт: серверной реализации API в задании нет.
