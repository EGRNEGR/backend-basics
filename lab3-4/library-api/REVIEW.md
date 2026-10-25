# REVIEW.md - саморевью контракта

Саморевью `openapi.yaml` по таблице «Как ревьюить API-контракт» (слайд 31) и
финальному чек-листу (слайды 32-35). Колонка «Где» указывает место в контракте.

## Таблица «Хорошо / Красный флаг» (слайд 31)

| Критерий | Результат | Где / комментарий |
|---|---|---|
| Ресурсы | ✅ `/books`, `/readers/{reader_id}`, `/loans/{loan_id}/return`; нет `/getBook`, `/do` или `action` в теле | `paths` |
| HTTP-коды | ✅ 201 на создание, 204 на удаление, 404 для ресурса по id, 409/422 на ошибки; нигде нет «200 на ошибку» | все операции |
| Списки | ✅ фильтры, `sort`, `limit`/`offset`, `limit.maximum = 100` | `GET /books`, `/readers`, `/loans`; `components.parameters.Limit` |
| Схемы | ✅ request/response разделены, есть `required`, `enum` (`LoanStatus`, `ErrorCode`, `sort`), nullable `returned_at` | `components.schemas` |
| Ошибки | ✅ один `ErrorResponse`, стабильный `code`, `request_id` | `ErrorResponse`, `ErrorCode` |
| Бизнес-правила | ✅ все 409/422 описаны с examples: `no_available_copies`, `active_loans_limit`, `has_active_loans`, `below_active_loans`, `must_be_in_future` | `POST /loans`, `DELETE /books/{book_id}`, `DELETE /readers/{reader_id}`, `PATCH /books/{book_id}` |
| Повторы | ✅ `Idempotency-Key` обязателен на `POST /loans` - двойной клик не создаёт дубль | `components.parameters.IdempotencyKey`, description `createLoan` |
| Документация | ✅ у всех операций есть `summary`, `description`, `tags`; общие части через `$ref`; тест проверяет 57 пар «example - схема» | весь файл |

## Финальный чек-лист

### Ресурсы и URL (слайд 32)

- [x] Path - существительные, множественное число, kebab-case.
- [x] Нет глагольных URL, кроме осознанного действия `/loans/{loan_id}/return`.
- [x] id конкретного ресурса - в path, фильтры - в query (`/loans?reader_id=7&status=overdue`).
- [x] Версия API указана в `servers` (`/v1`).

### Методы и коды (слайд 33)

- [x] POST создания возвращает `201` + `Location` (`createBook`, `createReader`, `createLoan`).
- [x] DELETE возвращает `204` без тела.
- [x] Пустой список - `200` + пустой `data` (пример `empty_page` у `GET /books`).
- [x] Бизнес-конфликт - `409`, ошибка валидации - `422`.

### Ошибки и списки (слайд 34)

- [x] Все ошибки используют один `ErrorResponse`.
- [x] Для `422` есть example с `details` (`validation_failed` у `POST /books`, `due_date_in_past` у `POST /loans`).
- [x] На коллекциях есть фильтры, сортировка и пагинация.
- [x] `limit` имеет `default: 20` и `maximum: 100`.

### Документация (слайд 35)

- [x] Операции имеют `summary`, `description`, `tags`.
- [x] Есть examples успеха и типичной ошибки.
- [x] Общие схемы подключены через `$ref`, не скопированы руками (`Book`, `Pagination`, `ErrorResponse`, параметры `Limit`/`Offset`/`*Id`, ответы `NotFound`/`Unauthorized`/...).
- [x] Файл OpenAPI валидируется без ошибок: `openapi-spec-validator` - OK, `redocly lint` - valid.

## Найдено инструментами и исправлено

1. YAML не парсился из-за `: ` внутри непроцитированного description у
   `securitySchemes` - нашёл `openapi-spec-validator`, взял строку в кавычки.
2. Prism отдавал `Idempotent-Replayed: null` - у заголовка не было example. Добавил `example: false`.
3. `redocly lint` предупреждал о серверах на `example.com`. Это намеренные плейсхолдеры
   учебного контракта, правило `no-server-example.com` отключено в `redocly.yaml` с комментарием.

## Решения, принятые при проектировании

1. `available_copies` есть только в response-схеме `Book` (`readOnly`). Request-схемы
   `CreateBookRequest` / `UpdateBookRequest` его не содержат и запрещают неизвестные
   поля (`additionalProperties: false`), поэтому клиент не может передать серверное поле.
2. `PATCH /books/{book_id}` не даёт уменьшить `total_copies` ниже числа активных
   выдач (`409 BUSINESS_RULE_VIOLATION`, `below_active_loans`), иначе `available_copies`
   стал бы отрицательным.
3. Возврат уже закрытой выдачи естественно идемпотентен: повтор возвращает `200` с тем же
   `returned_at`, поэтому `POST /loans/{loan_id}/return` не требует `Idempotency-Key`.

## Осознанные компромиссы

- **401 и код `UNAUTHORIZED`.** В требованиях нет кода для аутентификации, но после
  добавления Bearer JWT (бонус) каждая операция может вернуть 401. Добавил
  `UNAUTHORIZED` в `ErrorCode`, остальные 6 кодов - ровно из требований.
- **`IDEMPOTENCY_MISMATCH` - 422, конкурентный повтор - 409.** Так же, как в черновике
  IETF `Idempotency-Key` HTTP header: тело понятно, но не совпадает с сохранённым (422);
  ресурс в процессе изменения (409).
- **offset-пагинация**, а не cursor: списки библиотеки небольшие и меняются редко,
  а `total` нужен для UI с номерами страниц. При росте данных `GET /loans` можно
  перевести на cursor в v2.
- **`Retry-After` объявлен на весь ответ `409` `POST /loans`**, хотя имеет смысл только
  для конкурентного повтора: OpenAPI не позволяет привязать заголовок к отдельному
  example. В description заголовка это оговорено.
