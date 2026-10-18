import argparse
import json
import logging
import re
import sys

from logging_setup import configure_logging, set_run_id
from processing.errors import ApiError, CityNotFoundError, CurrencyNotFoundError
from processing.service import build_city_summary


def currency_code(value: str) -> str:
    normalized = value.upper()
    if not re.fullmatch(r"[A-Z]{3}", normalized):
        raise argparse.ArgumentTypeError("укажите трёхбуквенный ISO-код валюты")
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Погода и курс валюты для города")
    parser.add_argument("--city", required=True, help="название города")
    parser.add_argument(
        "--currency",
        type=currency_code,
        default="USD",
        help="ISO-код валюты (по умолчанию USD)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="вывести сводку в формате JSON",
    )
    return parser.parse_args()


def print_summary(summary: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    weather = summary["weather"]
    rates = summary["rates"]
    assert isinstance(weather, dict)
    assert isinstance(rates, dict)
    temperature = weather["temp_c"]
    description = weather["description"]
    warm_clothes = weather["warm_clothes"]
    currency = rates["currency"]
    rate = rates["rate_to_rub"]
    expensive = rates["expensive"]
    print(f"Город: {summary['city']}")
    print(f"Погода: {temperature:.1f}°C, {description}")
    print(f"Тёплая одежда: {'да' if warm_clothes else 'нет'}")
    print(f"{currency}→RUB: {rate:.2f}")
    print(f"Дорогой курс: {'да' if expensive else 'нет'}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    configure_logging()
    set_run_id()
    logger = logging.getLogger(__name__)
    logger.info("Starting city summary")

    try:
        summary = build_city_summary(args.city, args.currency)
    except (CityNotFoundError, CurrencyNotFoundError) as error:
        logger.warning("Requested resource was not found: %s", error)
        print(f"Ошибка: {error}", file=sys.stderr)
        return 3
    except ApiError as error:
        logger.error("External API request failed: %s", error)
        print(f"Ошибка внешнего сервиса: {error}", file=sys.stderr)
        return 4

    print_summary(summary, args.json)
    logger.info("City summary completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
