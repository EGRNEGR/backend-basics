class ApiError(Exception):
    """Base class for errors returned to the CLI as service failures."""


class ApiNotFoundError(ApiError):
    """Raised when an API returns HTTP 404."""


class ApiStatusError(ApiError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"внешний сервис вернул HTTP {status_code}")


class InvalidApiResponseError(ApiError):
    """Raised when an API response is missing required fields or has bad JSON."""


class CityNotFoundError(Exception):
    """Raised when the geocoder has no match for a city."""


class CurrencyNotFoundError(Exception):
    """Raised when Frankfurter does not recognize a currency code."""
