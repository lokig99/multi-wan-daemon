from typing import Any

import requests

from cache import Cache
from config import DefaultsMissingException, get_settings_value


class GandiConfig:
    """
    The Gandi.net configuration class used by the `GandiClient` class.
    """

    def __init__(self, domain: str, apikey: str) -> None:
        """
        Create a new `GandiConfig` instance.

        Parameters: 
        ----------
            `domain` (str): The domain name to update. For example: `example.com`
            `apikey` (str): The API key for the Gandi.net LiveDNS API.
        """
        self.apikey = apikey
        """The API key for the Gandi.net LiveDNS API."""
        self.domain = domain
        """The domain name to manage. For example: `example.com`"""

    @staticmethod
    def defaults() -> 'GandiConfig':
        """
        Create a new `GandiConfig` instance with the default values from the settings file or from the environment if the file does not exist. If the file does exist then environment variables will be ignored.

        Raises:
        ------
            - `DefaultsMissingException` - If the required default values are missing.

        Returns:
        --------
            `GandiConfig`: The config with the default values.
        """
        api_key = get_settings_value('gandi', 'apikey', 'GANDI_API_KEY')
        domain = get_settings_value('gandi', 'domain', 'GANDI_DOMAIN')
        if not api_key or not domain:
            missing = (v[1] for v in ((api_key, 'apikey'),
                       (domain, 'domain')) if not v[0])
            raise DefaultsMissingException(
                f'Gandi.net config is incomplete, fields missing: {", ".join(missing)}')
        return GandiConfig(domain, api_key)


class GandiClient:
    """
    The Gandi.net client class used to manage the domain record.

    Usage:
    ------
        >>> client = GandiClient(config)
        >>> client.domain_ip()
        '1.2.3.4'
        >>> client.set_domain_ip('5.6.7.8')
        >>> true
    """
    class Consts:
        """
        The constants class used to store the constants for the `GandiClient` class.
        """
        __MAIN_RECORD_URL__ = 'https://api.gandi.net/v5/livedns/domains/{domain}/records/%40/A'

        def __init__(self, domain: str) -> None:
            """
            Create a new `Consts` instance with the given domain.

            Args:
            -----
                `domain` (str) - The domain name to manage. For example: `example.com`
            """
            self.MAIN_RECORD_URL = self.__MAIN_RECORD_URL__.format(
                domain=domain)

    class CacheKeys:
        """
        The cache keys class used to store the cache keys for the `GandiClient` class.
        """
        DOMAIN_IP = 'domip'
        """The cache key for the domain IP address."""

    def __init__(self, config: GandiConfig) -> None:
        self.__domain = config.domain
        """The domain name to manage. For example: `example.com`"""
        self.__apikey = config.apikey
        """The API key for the Gandi.net LiveDNS API."""
        self.__cache = Cache()
        """The cache used to store the IP address of the domain."""
        self.__consts = self.Consts(self.__domain)
        """The constants used by the client."""

    @staticmethod
    def with_default_config() -> 'GandiClient':
        """
        Create a new `GandiClient` instance with the default config from the settings file or from the environment if the file does not exist.

        Returns:
        --------
            `GandiClient`: The client with the default config.
        """
        return GandiClient(GandiConfig.defaults())

    def __make_get_request(self, url: str, timeout=5) -> dict[str, Any]:
        response = requests.get(
            url, headers={'Authorization': f'Apikey {self.__apikey}'}, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def __make_put_request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        response = requests.put(
            url, headers={'Authorization': f'Apikey {self.__apikey}'}, json=body)
        response.raise_for_status()
        return response.json()

    def domain_ip(self) -> str:
        """
        Get the current IP address of the domain.

        Note:
            Uses the cache to store the IP address for 10 minutes.

        Returns:
        --------
            `str`: The IP address of the domain.
        """
        if not (ip := self.__cache[self.CacheKeys.DOMAIN_IP]):
            r = self.__make_get_request(self.__consts.MAIN_RECORD_URL)
            ip = r['rrset_values'][0]
            self.__cache[self.CacheKeys.DOMAIN_IP] = ip, 600
        return ip

    def set_domain_ip(self, ip: str) -> bool:
        """
        Set the IP address of the domain.

        Args:
        -----
            `ip` (str) - The IP address of the domain to set.

        Returns:
        --------
            `bool`: `True` if the IP address was set successfully, `False` otherwise.
        """
        record = {
            'rrset_type': 'A',
            'rrset_values': [ip],
            'rrset_ttl': 300
        }
        r = self.__make_put_request(self.__consts.MAIN_RECORD_URL, record)
        success = r['message'] == 'DNS Record Created'
        del self.__cache[self.CacheKeys.DOMAIN_IP]
        if success:
            self.__cache[self.CacheKeys.DOMAIN_IP] = ip, 600
        return success
