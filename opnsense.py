from dataclasses import dataclass
from typing import Any

import requests

from cache import Cache
from config import (DefaultsMissingException, Interface, get_interfaces,
                    get_settings_value)


class OpnSenseConfig:
    """
    The `OpnSenseConfig` class defines the configuration for the `OpnSenseClient` class.
    """
    __DEFAULT_TIMEOUT__ = 5

    def __init__(self, host: str, key: str, secret: str, wans: list[Interface], use_https: bool = True, timeout=__DEFAULT_TIMEOUT__) -> None:
        """
        Create a new `OpnSenseConfig` instance.

        Args:
        -----
            - `host` (str): The hostname or IP address of the OPNsense server.
            - `key` (str): The API key for the OPNsense server.
            - `secret` (str): The API secret for the OPNsense server.
            - `wans` (list[Interface]): The list of WAN interfaces in a form of `Interface` objects.
            - `use_https` (bool, optional): Whether to use HTTPS or HTTP. Defaults to `True`.
            - `timeout` (_type_, optional): The timeout for requests in seconds. Defaults to `5`.
        """
        self.host = host
        """The hostname or IP address of the OPNsense server."""
        self.key = key
        """The API key for the OPNsense server."""
        self.secret = secret
        """The API secret for the OPNsense server."""
        self.wans = wans
        """The list of WAN interfaces in a form of `Interface` objects."""
        self.use_https = use_https
        """The protocol to use for requests."""
        self.timeout = timeout
        """The timeout for requests in seconds."""

    @staticmethod
    def defaults() -> 'OpnSenseConfig':
        """
        Get the default configuration for the `OpnSenseClient` class from the environment variables or the settings JSON file.

        Raises:
        -------
            `DefaultsMissingException` - If any of the required fields are missing.

        Returns:
        --------
            `OpnSenseConfig` - The default configuration for the `OpnSenseClient` class.
        """
        host = get_settings_value('opnsense', 'host', 'OPNSENSE_HOST')
        key = get_settings_value('opnsense', 'key', 'OPNSENSE_KEY')
        secret = get_settings_value('opnsense', 'secret', 'OPNSENSE_SECRET')
        timeout = int(t) if (t := get_settings_value(
            'opnsense', 'timeout', 'OPNSENSE_TIMEOUT')) else OpnSenseConfig.__DEFAULT_TIMEOUT__
        use_https = https if (https := get_settings_value(
            'opnsense', 'use_https', 'OPNSENSE_USE_HTTPS')) else True
        wans: list[Interface] = get_interfaces()
        if not host or not key or not secret or not wans:
            missing = (v[1] for v in ((host, 'host'), (key, 'key'),
                       (secret, 'secret'), (wans, 'interfaces (wans)')) if not v[0])
            raise DefaultsMissingException(
                f'OPNsense config is incomplete, fields missing: {", ".join(missing)}')
        return OpnSenseConfig(host, key, secret, wans, use_https, timeout)

@dataclass
class Gateway(Interface):
    """
    The `Gateway` class defines a WAN interface with additional information about the assigned IP address. It extends the `Interface` class.
    """
    
    ip: str
    """The IP address of the gateway."""

    @staticmethod
    def from_interface(interface: Interface, ip: str) -> 'Gateway':
        """
        Create a new `Gateway` instance from an `Interface` instance.

        Args:
        -----
            - `interface` (Interface): The `Interface` instance to create the `Gateway` instance from.
            - `ip` (str): The IP address of the gateway.

        Returns:
        --------
            `Gateway` - The new `Gateway` instance.
        """
        return Gateway(interface.name, interface.id, interface.priority, ip)


class OpnSenseClient:
    """
    The `OpnSenseClient` class provides an interface for interacting with an OpenSense API server. It is used to get information about the WAN interfaces and to set the active WAN interface.

    The client uses its own cache to store the results of API calls. The cache is not shared with other clients. The cache is cleared when the `OpnSenseClient` instance is destroyed.

    Usage:
    -------
        >>> client = OpnSenseClient(config)
        >>> client.all_gateways()
        {'wan1': ('1.2.3.4', 100, '1.0.0.0'), 'wan2': ('5.6.7.8', 50, '2.0.0.0')}
        >>> client.active_gateway()
        ('wan1', '1.2.3.4', '1.0.0.0')
    """

    class Consts:
        """
        The `Consts` class defines constant values used in the `OpnSenseClient` class.

        Attributes:
        ----------
            - `ACTIVE_WAN_ALIAS` - The name of the alias for the active WAN interface.
            - `ACTIVE_WAN_ID_ALIAS` - The name of the alias for the ID of the active WAN interface.
            - `INTERFACE_CONFING_URL` - The URL for the API endpoint for getting interface configuration information.

        Examples:
        ----------
            >>> consts = Consts('myapi.example.com', True)
            >>> consts.INTERFACE_CONFING_URL
            'https://myapi.example.com/api/diagnostics/interface/getInterfaceConfig'
            >>> consts.get_alias_url('MyAlias')
            'https://myapi.example.com/api/firewall/alias_util/list/MyAlias'
        """
        __INTERFACE_CONFING_URL__ = '{protocol}://{host}/api/diagnostics/interface/getInterfaceConfig'
        ACTIVE_WAN_ALIAS = 'Active_WAN'
        """The name of the alias for the active WAN interface."""
        ACTIVE_WAN_ID_ALIAS = 'Active_WAN_Id'
        """The name of the alias for the ID of the active WAN interface."""
        __GET_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/list/{alias}'
        """The URL template for the API endpoint for getting information about an alias."""
        __ADD_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/add/{alias}'
        """The URL template for the API endpoint for adding an alias."""
        __DELETE_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/delete/{alias}'
        """The URL template for the API endpoint for deleting an alias."""

        def __init__(self, host: str, use_https: bool) -> None:
            """
            Initializes the `Consts` class with the given protocol and host information.

            Args:
            -----
                - `host` - The hostname of the API server.
                - `use_https` - A flag indicating whether to use HTTPS for API requests.

            Examples:
            ----------
                >>> consts = Consts('my.opnsense-hostname.com', True)
                >>> consts.INTERFACE_CONFING_URL
                'https://my.opnsense-hostname.com/api/diagnostics/interface/getInterfaceConfig'
            """
            self.__host = host
            self.__protocol = 'https' if use_https else 'http'
            self.INTERFACE_CONFING_URL = self.__INTERFACE_CONFING_URL__.format(
                protocol=self.__protocol, host=host)
            """The URL for the API endpoint for getting interface configuration information."""

        def get_alias_url(self, alias: str) -> str:
            """
            Returns the URL for the API endpoint for getting information about the given alias.

            Args:
            -----
               - `alias` - The name of the alias to get information about.

            Returns:
            --------
                `str` - The URL for the API endpoint for getting information about the given alias.
            """
            return self.__GET_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

        def add_alias_url(self, alias: str) -> str:
            """
            Returns the URL for the API endpoint for adding the given alias.

            Args:
            -----
                - `alias` (str): The name of the alias to add.

            Returns:
            --------
                `str` - The URL for the API endpoint for adding the given alias.
            """
            return self.__ADD_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

        def delete_alias_url(self, alias: str) -> str:
            """
            Returns the URL for the API endpoint for deleting the given alias.

            Args:
            -----
                - `alias` (str) - The name of the alias to delete.

            Returns:
            --------
                `str` - The URL for the API endpoint for deleting the given alias.
            """
            return self.__DELETE_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

    class CacheKeys:
        """
        The `CacheKeys` class defines the keys used for caching information in the `OpnSenseClient` class.
        """
        ALL_GATEWAYS = 'allactgw'
        """The key for caching the result of the `all_gateways` method."""
        ACTIVE_GATEWAY_ID = 'actgwid'
        """The key for caching the current value of the active gateway's ID."""
        ACTIVE_GATEWAY = 'actgw'
        """The key for caching the `Gateway` object for the active gateway."""
        ACTIVE_GATEWAY_IP = 'actgwip'
        """The key for caching the current value of the active gateway's IP address."""

    def __init__(self, config: OpnSenseConfig) -> None:
        """
        Creates a new instance of the `OpnSenseClient` class.

        Args:
        -----
            - `config` (OpnSenseConfig) - The configuration to use for the client.

        Returns:
        --------
            `OpnSenseClient` - A new instance of the `OpnSenseClient` class set with the given configuration.
        """
        self.__host = config.host
        """The hostname of the API server."""
        self.__wans = config.wans[:]
        """A list of WAN interfaces to use represtented by `cfg.Interface` objects."""
        self.__key = config.key
        """The API key for authenticating with the API server."""
        self.__secret = config.secret
        """The API secret for authenticating with the API server."""
        self.__cache = Cache()
        """An internal cache for storing information to avoid making unnecessary repeated requests to the API server."""
        self.__consts = self.Consts(self.__host, config.use_https)
        """An instance of the `Consts` class, which defines constant values used in the `OpnSenseClient` class."""
        self.__timeout = config.timeout
        """The maximum amount of time to wait for a response from the API server."""

    @staticmethod
    def with_default_config() -> 'OpnSenseClient':
        """
        Creates a new instance of the `OpnSenseClient` class using the default configuration from the environment or settings JSON file if available.

        Raises:
        -------
            - `DefaultsMissingException` - If the default configuration is not available or is incomplete.

        Returns:
        --------
            `OpnSenseClient` - A new instance of the `OpnSenseClient` class using the default configuration.
        """
        return OpnSenseClient(OpnSenseConfig.defaults())

    def __make_get_request(self, url: str) -> dict[str, Any]:
        response = requests.get(url, auth=(
            self.__key, self.__secret), timeout=self.__timeout)
        response.raise_for_status()
        return response.json()

    def __make_post_request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            url, json=body,  auth=(self.__key, self.__secret))
        response.raise_for_status()
        return response.json()

    def all_gateways(self) -> dict[str, Gateway]:
        """
        Get a dictionary of all available gateways.

        Returns:
        --------
            `dict[str, Gateway]` - A dictionary of all available gateways, where the keys are the names of the gateways and the values are `Gateway` objects.
        """
        if not (gateways := self.__cache[self.CacheKeys.ALL_GATEWAYS]):
            r = self.__make_get_request(self.__consts.INTERFACE_CONFING_URL)
            gateways = {}
            for wan, priority, id in ((w.name, w.priority, w.id) for w in self.__wans):
                if wan in r and (ipv4 := r[wan]['ipv4']):
                    gateways[wan] = Gateway(
                        wan, id, priority,  ipv4[0]['ipaddr'])
            self.__cache[self.CacheKeys.ALL_GATEWAYS] = gateways, 5
        return gateways

    def __get_wan_by_id(self, id: str) -> Interface:
        for wan in self.__wans:
            if wan.id == id:
                return wan
        raise ValueError(f'No WAN interface found with ID "{id}".')

    def active_gateway(self) -> Gateway:
        """
        Get the active gateway as a `Gateway` object.

        Raises:
        -------
            - `ValueError` - If the active gateway cannot be determined, because the active gateway ID is not set or the Interace with the given ID is not configured as a WAN interface.

        Returns:
        --------
            `Gateway`: The active gateway as a `Gateway` object.
        """
        def get_alias_value(alias: str, cache_key: str) -> str:
            if not (value := self.__cache[cache_key]):
                url = self.__consts.get_alias_url(alias)
                r = self.__make_get_request(url)
                value = r['rows'][0]['ip']
                self.__cache[cache_key] = value, 300
            return value

        if gw := self.__cache[self.CacheKeys.ACTIVE_GATEWAY]:
            return gw

        ip = get_alias_value(self.Consts.ACTIVE_WAN_ALIAS,
                             self.CacheKeys.ACTIVE_GATEWAY_IP)
        id = get_alias_value(self.Consts.ACTIVE_WAN_ID_ALIAS,
                             self.CacheKeys.ACTIVE_GATEWAY_ID)
        try:
            wan = self.__get_wan_by_id(id)
        except ValueError:
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP]
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]
            raise

        active_gw = Gateway.from_interface(wan, ip)
        self.__cache[self.CacheKeys.ACTIVE_GATEWAY] = active_gw, 300
        return active_gw

    def update_active_gateway(self, wan_name: str | None = None) -> bool:
        """
        Update the active gateway.
        Set the active gateway to the gateway with the given name, or update the currently selected gateway's IP address if the address has changed.

        Args:
        -----
            `wan_name` (str | None, optional) - The name of the gateway to set as the active gateway or `None` to update the currently selected gateway's IP address. Defaults to `None`.

        Returns:
        --------
            `bool`: `True` if the active gateway was updated successfully, otherwise `False`.
        """
        def set_alias(alias: str, new_value: str, old_value: str) -> bool:
            # delete old entry
            url = self.__consts.delete_alias_url(alias)
            r = self.__make_post_request(url, {'address': old_value})
            if r['status'] == 'failed':
                return False

            # add new entry
            url = self.__consts.add_alias_url(alias)
            r = self.__make_post_request(url, {'address': new_value})
            if r['status'] == 'failed':
                return False

            return True

        def set_active_wan(new_ip: str, old_ip: str) -> bool:
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP]
            if set_alias(self.__consts.ACTIVE_WAN_ALIAS, new_ip, old_ip):
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP] = ip, 300
                return True
            return False

        def set_active_wan_id(new_id: str) -> bool:
            if not (old_id := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]):
                url = self.__consts.get_alias_url(
                    self.__consts.ACTIVE_WAN_ID_ALIAS)
                r = self.__make_get_request(url)
                old_id = r['rows'][0]['ip']

            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]
            if set_alias(self.__consts.ACTIVE_WAN_ID_ALIAS, new_id, old_id):
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID] = id, 300
                return True
            return False

        gateways = self.all_gateways()
        if wan_name and wan_name not in gateways:
            return False

        old_gw = self.active_gateway()

        # new active WAN name has been provided as parameter
        if wan_name and wan_name != old_gw.name and wan_name in gateways:
            new_gw = gateways[wan_name]
            return set_active_wan(new_gw.ip, old_gw.ip) and set_active_wan_id(new_gw.id)

        # update current active WAN IP address
        elif old_gw.name and old_gw.name in gateways and (ip := gateways[old_gw.name].ip) != old_gw.ip:
            return set_active_wan(ip, old_gw.ip)

        return False
    
    def priority_gateway(self) -> Gateway:
        """
        Get the gateway with the highest priority from all available gateways. 
        
        note: If multiple gateways have the same priority, the gateway with the lowest name will be returned.
        

        Returns:
        --------
        `Gateway`: The gateway with the highest priority.
        """
        available_gateways = self.all_gateways()
        _, priority_gateway = min(available_gateways.items(),
                              key=lambda item: item[1].priority)
        return priority_gateway
