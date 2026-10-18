# Сводка по городу

CLI получает текущую погоду из Open-Meteo и курс валюты к рублю из Frankfurter, затем добавляет флаги для тёплой одежды и дорогого курса.

## Требования

- Python 3.12
- Зависимость `requests` из `requirements.txt`
- API-ключи не нужны

## Установка и запуск

```bash
python -m pip install -r requirements.txt
python main.py --city Moscow
python main.py --city Moscow --currency EUR
```

Для структурированного вывода используйте `--json`:

```bash
python main.py --city Moscow --currency EUR --json
```

Погода поступает из [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api) и [Weather Forecast API](https://open-meteo.com/en/docs). Курс запрашивается через [Frankfurter API v2](https://frankfurter.dev/).

На временные сетевые ошибки и HTTP 500, 502, 503, 504 выполняются до трёх попыток. Для HTTP 429 учитывается числовой `Retry-After`. Внешние ответы проверяются перед использованием. Ошибки аргументов завершаются кодом 2, неизвестный город или валютный код — 3, сбой внешнего сервиса — 4.
