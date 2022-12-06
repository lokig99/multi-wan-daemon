import time
from typing import Any


class Cache:
    """
    A dictionary-like object for storing values associated with keys.

    The Cache automatically removes items after a specified amount of time has
    passed (known as a `timeout`).

    Usage:
        >>> cache = Cache()
        >>> cache['k1'] = 'value', 5  # Add a new key/value pair with a timeout of 5 seconds
        >>> cache['k1']
        'value'
        >>> time.sleep(10)
        >>> cache['k1']
        None
        >>> del cache['k1']  # Delete key/value pair
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

    def __setitem__(self, key: str, value: tuple[Any, float]):
        item, timeout = value
        expiration_time = time.time() + timeout
        self.__store[key] = item, expiration_time
