import datetime
import time
from typing import Any


class Cache:
    """
    A dictionary-like object for storing values associated with keys.

    The Cache automatically removes items after a specified amount of time has
    passed (known as a `timeout`).

    Usage:
    ------
        >>> cache = Cache()
        >>> cache['k1'] = 'value', 5  # Add a new key/value pair with a timeout of 5 seconds
        >>> cache['k1']
        'value'
        >>> cache.expires_in('k1')
        5.0
        >>> time.sleep(10)
        >>> cache['k1']
        None
        >>> del cache['k1']  # Delete key/value pair

    Raises:
    -------
        - `ValueError` timeout must be a positive number

        - `TypeError` timeout must be a number

        >>> cache['k1'] = 'value', -1
        ValueError: Timeout must be a positive number, not '-1'
        >>> cache['k1'] = 'value', 'invalid'
        TypeError: Timeout must be a number, not 'str'

    """

    def __init__(self) -> None:
        self.__store: dict[str, tuple[Any, float]] = {}

    def __contains__(self, key: str) -> bool:
        if key in self.__store:
            _, expiration_time = self.__store[key]
            now = time.time()
            if now < expiration_time:
                return True
            # value expired
            del self.__store[key]
        return False

    def __getitem__(self, key: str) -> Any | None:
        if key in self:
            value, _ = self.__store[key]
            return value
        return None

    def __delitem__(self, key: str):
        if key in self:
            del self.__store[key]

    @staticmethod
    def __validate_timeout(timeout: float) -> None:
        is_number = isinstance(timeout, float) or isinstance(timeout, int)
        if is_number and timeout > 0:
            return  # timeout is valid
        if is_number and timeout <= 0:
            # timeout cannot be less than or equal to 0
            raise ValueError(
                f"Timeout must be a positive number, not '{timeout}'")
        if not is_number:
            # timeout must be a number
            raise TypeError(
                f"Timeout must be a number, not '{type(timeout).__name__}'")

    def __setitem__(self, key: str, value: tuple[Any, float]):
        """
        Set the value and the timeout of a key.

        Args:
            `key` (str): The key to set the value of.
            `value` (tuple[Any, float]): The tuple containing the value and the timeout in seconds.

        Throws:
            `ValueError` timeout must be a positive number
            `TypeError` timeout must be a number
        """
        item, timeout = value
        Cache.__validate_timeout(timeout)
        expiration_time = time.time() + timeout
        self.__store[key] = item, expiration_time

    def __repr__(self) -> str:
        return str(self.__store)

    def expiration_time(self, key: str) -> float | None:
        """
        Get the expiration time of a key in a form of a UNIX timestamp.

        Args:
            `key` (str): The key to get the expiration time of.

        Returns:
            `float` | `None`: The expiration time of the key in a form of a UNIX timestamp or `None` if the key does not exist.

        Example:
            >>> cache.expiration_datetime('k1')
            1621234567.890123
        """
        if key in self:
            _, expiration_time = self.__store[key]
            return expiration_time
        return None

    def expiration_datetime(self, key: str) -> datetime.datetime | None:
        """
        Get the expiration time of a key in a form of a `datetime.datetime` object.

        Args:
        ----
            `key` (str): The key to get the expiration time of.

        Returns:
        -------
            `datetime.datetime` | `None`: The expiration time of the key in a form of a `datetime.datetime` object or `None` if the key does not exist.

        Example:
        -------
            >>> cache.expiration_datetime('k1')
            datetime.datetime(2021, 5, 18, 12, 34, 56, 789012)
        """
        if time := self.expiration_time(key):
            return datetime.datetime.fromtimestamp(time)
        return None

    def expires_in(self, key: str) -> float | None:
        """
        Get the amount of time in seconds until a key expires.

        Args:
        ----
            `key` (str): The key to get the expiration time of.

        Returns:
        -------
            `float` | `None`: The amount of time until a key expires or `None` if the key does not exist.

        Example:
        -------
            >>> cache.expires_in('k1')
            5.0
        """
        if timestamp := self.expiration_time(key):
            return timestamp - time.time()
        return None
