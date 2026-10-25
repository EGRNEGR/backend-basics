# Library API - контракт сервиса «Библиотека» (ДЗ3)

OpenAPI 3.1 контракт сервиса «Библиотека»: книги, читатели, выдачи.

| Файл | Содержимое |
|---|---|
| [`openapi.yaml`](openapi.yaml) | Контракт: 14 операций, схемы, ошибки, examples |
| [`STYLE.md`](STYLE.md) | 10 правил API, которым следует контракт |
| [`REVIEW.md`](REVIEW.md) | Саморевью по чек-листу со слайдов 31-35 |
| [`redocly.yaml`](redocly.yaml) | Конфигурация линтера Redocly |

## Операции

| Метод и путь | Назначение | Успех | Ошибки |
|---|---|---|---|
| `GET /books` | Список книг с фильтрами | 200 | 400, 401 |
| `POST /books` | Добавить книгу | 201 + Location | 400, 401, 409, 422 |
| `GET /books/{book_id}` | Получить книгу | 200 | 401, 404 |
| `PATCH /books/{book_id}` | Изменить книгу | 200 | 400, 401, 404, 409, 422 |
| `DELETE /books/{book_id}` | Удалить книгу | 204 | 401, 404, 409 |
| `GET /readers` | Список читателей | 200 | 400, 401 |
| `POST /readers` | Зарегистрировать читателя | 201 + Location | 400, 401, 409, 422 |
| `GET /readers/{reader_id}` | Получить читателя | 200 | 401, 404 |
| `PATCH /readers/{reader_id}` | Изменить читателя | 200 | 400, 401, 404, 409, 422 |
| `DELETE /readers/{reader_id}` | Удалить читателя | 204 | 401, 404, 409 |
| `GET /loans` | Список выдач, `?status=overdue` | 200 | 400, 401 |
| `POST /loans` | Выдать книгу (Idempotency-Key) | 201 + Location | 400, 401, 404, 409, 422 |
| `GET /loans/{loan_id}` | Получить выдачу | 200 | 401, 404 |
| `POST /loans/{loan_id}/return` | Вернуть книгу | 200 | 401, 404 |

## Как бизнес-правила отражены в контракте

| Правило | Где в контракте |
|---|---|
| Выдача только при `available_copies > 0` | `POST /loans` → `409 BUSINESS_RULE_VIOLATION`, example `no_available_copies` |
| Не более 5 активных выдач на читателя | `POST /loans` → `409`, example `active_loans_limit` |
| Возврат через `POST /loans/{id}/return` | отдельная операция `returnLoan`, `DELETE /loans/{id}` отсутствует |
| Просроченные: `GET /loans?status=overdue` | параметр `status` с enum `LoanStatus`, example `overdue` |
| Нельзя удалить книгу/читателя с активными выдачами | `DELETE` → `409`, examples `book_has_active_loans`, `reader_has_active_loans` |
| `due_date` позже текущей даты | `POST /loans` → `422 VALIDATION_ERROR`, example `due_date_in_past` |
| `available_copies` вычисляет сервер | `readOnly` в `Book`, отсутствует в request-схемах, которые запрещают лишние поля |
| Idempotency-Key на `POST /loans` | обязательный header (uuid), таблица replay / mismatch / конкурентный повтор / 24 часа в description |

## Проверка контракта

```bash
# из корня репозитория, с активированным .venv
python -m pip install -r lab3-4/requirements.txt
openapi-spec-validator lab3-4/library-api/openapi.yaml
python -m pytest lab3-4/tests/test_library_contract.py

# линтер Redocly (нужен Node.js)
cd lab3-4/library-api && npx @redocly/cli lint openapi.yaml
```

## Дополнительное задание

Выполнены все четыре пункта.

### 1. Mock-сервер и curl

```bash
cd lab3-4/library-api
npx @stoplight/prism-cli@5 mock openapi.yaml -p 4010
```

Prism берёт ответы из examples контракта и валидирует запросы по схемам.
Ниже - реальный вывод запросов к mock (служебные заголовки CORS опущены).

Просроченные выдачи:

```console
$ curl -i "http://127.0.0.1:4010/loans?status=overdue" -H "Authorization: Bearer test-token"
HTTP/1.1 200 OK
Content-type: application/json

{"data":[{"id":1001,"book_id":42,"reader_id":7,"loaned_at":"2026-09-01T10:00:00Z","due_date":"2026-09-15T10:00:00Z","returned_at":null,"status":"overdue","is_overdue":true}],"pagination":{"limit":20,"offset":0,"total":1}}
```

Создание выдачи с Idempotency-Key:

```console
$ curl -i -X POST http://127.0.0.1:4010/loans \
    -H "Authorization: Bearer test-token" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: 6f1c2a7e-0d43-4b8a-9a4e-2f6b1d3c9e10" \
    -d '{"book_id":42,"reader_id":7,"due_date":"2026-11-08T18:00:00Z"}'
HTTP/1.1 201 Created
Idempotent-Replayed: false
Location: /v1/loans/1002
Content-type: application/json

{"id":1002,"book_id":42,"reader_id":7,"loaned_at":"2026-10-25T12:00:00Z","due_date":"2026-11-08T18:00:00Z","returned_at":null,"status":"active","is_overdue":false}
```

Бизнес-ошибка (example выбирается заголовком `Prefer`):

```console
$ curl -i -X POST http://127.0.0.1:4010/loans \
    -H "Authorization: Bearer test-token" \
    -H "Content-Type: application/json" \
    -H "Prefer: code=409, example=no_available_copies" \
    -H "Idempotency-Key: 6f1c2a7e-0d43-4b8a-9a4e-2f6b1d3c9e10" \
    -d '{"book_id":42,"reader_id":7,"due_date":"2026-11-08T18:00:00Z"}'
HTTP/1.1 409 Conflict
Retry-After: 1
Content-type: application/json

{"error":{"code":"BUSINESS_RULE_VIOLATION","message":"Нет свободных экземпляров книги","details":[{"field":"book_id","issue":"no_available_copies","message":"У книги 42 available_copies = 0"}],"request_id":"req_4d2f8a10"}}
```

Клиент передал серверное поле `available_copies` - mock отклоняет запрос по схеме:

```console
$ curl -i -X POST http://127.0.0.1:4010/books -H "Authorization: Bearer t" -H "Content-Type: application/json" \
    -d '{"title":"X","author":"Y","isbn":"9780547928227","published_year":1937,"total_copies":3,"available_copies":3}'
HTTP/1.1 422 Unprocessable Entity
sl-violations: [{"location":["request","body"],"severity":"Error","code":"additionalProperties","message":"Request body must NOT have additional properties; found 'available_copies'"}]
```

Запрос без токена - `401 Unauthorized` (`sl-violations: ... "Invalid security scheme used"`).

Ограничение mock: Prism не хранит состояние, поэтому реальный replay по
Idempotency-Key и проверки бизнес-правил он не выполняет - только отдаёт examples.
При отсутствии `Idempotency-Key` Prism отвечает `422` (своя валидация запроса),
тогда как контракт требует `400 INVALID_REQUEST`.

### 2. Авторизация Bearer JWT

`components.securitySchemes.bearer_auth` (`type: http`, `scheme: bearer`,
`bearerFormat: JWT`) подключена глобально через `security`. Все операции описывают
`401` с кодом `UNAUTHORIZED`. Subject токена задаёт область уникальности Idempotency-Key.

### 3. Устаревшее поле

`Loan.is_overdue` помечено `deprecated: true`: дублирует `status == "overdue"` и будет
удалено в v2. Пока поле возвращается, чтобы не сломать существующих клиентов.

### 4. Изменения при переходе к v2

| Изменение | Совместимо с v1? | Почему |
|---|---|---|
| Добавить необязательное поле в ответ (`Book.cover_url`) | ✅ да | Старые клиенты игнорируют неизвестные поля |
| Добавить необязательный query-фильтр (`GET /books?genre=`) | ✅ да | Старые запросы работают без изменений |
| Добавить новый endpoint (`GET /readers/{reader_id}/loans`) | ✅ да | Существующие операции не меняются |
| Увеличить `limit.maximum` со 100 до 200 | ✅ да | Все прежние значения остаются допустимыми |
| Добавить необязательное поле в request (`CreateLoanRequest.comment`) | ⚠️ условно | Клиенты v1 его не шлют - ок; но до раскатки сервера новые клиенты получат `422` из-за `additionalProperties: false` |
| Добавить значение в enum ответа (`LoanStatus.lost`) | ⚠️ осторожно | Клиент со строгим `switch` по статусу может упасть на новом значении |
| Удалить устаревшее `Loan.is_overdue` | ❌ нет | Клиенты могли на него опираться; поэтому сначала `deprecated` в v1 |
| Сделать `due_date` необязательной с серверным значением по умолчанию | ✅ да | Ослабление требований к запросу ничего не ломает |
| Сделать обязательным новое поле запроса (`CreateReaderRequest.phone`) | ❌ нет | Старые клиенты начнут получать `422` |
| Переименовать поле (`full_name` → `name`) или сменить тип (`id`: integer → uuid) | ❌ нет | Ломается парсинг на клиентах |
| Перейти с `offset` на `cursor`-пагинацию в `GET /loans` | ❌ нет | Меняются параметры запроса и структура `pagination` |
| Изменить код ответа (`IDEMPOTENCY_MISMATCH` 422 → 409) | ❌ нет | Клиенты обрабатывают ошибки по статусу и `code` |
