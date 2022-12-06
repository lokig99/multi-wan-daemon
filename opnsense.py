from typing import Any

import requests

from cache import Cache
from config import (DefaultsMissingException, Interface, get_interfaces,
                    get_settings_value)


class OpnSenseConfig:
    __DEFAULT_TIMEOUT__ = 5

    def __init__(self, host: str, key: str, secret: str, wans: list[Interface], use_https: bool = True, timeout=__DEFAULT_TIMEOUT__) -> None:
        self.host = host
        self.key = key
        self.secret = secret
        self.wans = wans
        self.use_https = use_https
        self.timeout = timeout

    @staticmethod
    def defaults() -> 'OpnSenseConfig':
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


class OpnSenseClient:
    """
    The `OpnSenseClient` class provides an interface for interacting with an OpenSense API server.

    Examples:
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
            `ACTIVE_WAN_ALIAS` The name of the alias for the active WAN interface.
            `ACTIVE_WAN_ID_ALIAS` The name of the alias for the ID of the active WAN interface.
            `INTERFACE_CONFING_URL` The URL for the API endpoint for getting interface configuration information.

        Examples:
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
                `host` The hostname of the API server.
                `use_https` A flag indicating whether to use HTTPS for API requests.

            Examples:
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
            """Returns the URL for the API endpoint for getting information about the given alias.

            Args:
                `alias` The name of the alias to get information about.

            Returns:
                The URL for the API endpoint for getting information about the given alias.
            """
            return self.__GET_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

        def add_alias_url(self, alias: str) -> str:
            return self.__ADD_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

        def delete_alias_url(self, alias: str) -> str:
            return self.__DELETE_ALIAS_URL__.format(protocol=self.__protocol, host=self.__host, alias=alias)

    class CacheKeys:
        ALL_GATEWAYS = 'allactgw'
        ACTIVE_GATEWAY_ID = 'actgwid'
        ACTIVE_GATEWAY_NAME = 'actgwname'
        ACTIVE_GATEWAY_IP = 'actgwip'

    def __init__(self, config: OpnSenseConfig) -> None:
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

    def all_gateways(self) -> dict[str, tuple[str, int, str]]:
        if not (gateways := self.__cache[self.CacheKeys.ALL_GATEWAYS]):
            r = self.__make_get_request(self.__consts.INTERFACE_CONFING_URL)
            # gateways: dict[str, tuple[str, int, str]]
            gateways = {}
            for wan, priority, id in ((w.name, w.priority, w.id) for w in self.__wans):
                if wan in r and (ipv4 := r[wan]['ipv4']):
                    gateways[wan] = ipv4[0]['ipaddr'], priority, id
            self.__cache[self.CacheKeys.ALL_GATEWAYS] = gateways, 5
        return gateways

    def active_gateway(self) -> tuple[str | None, str]:
        def get_alias_value(alias: str, cache_key: str) -> str:
            if not (value := self.__cache[cache_key]):
                url = self.__consts.get_alias_url(alias)
                r = self.__make_get_request(url)
                value = r['rows'][0]['ip']
                self.__cache[cache_key] = value, 300
            return value

        ip = get_alias_value(self.Consts.ACTIVE_WAN_ALIAS,
                             self.CacheKeys.ACTIVE_GATEWAY_IP)
        id = get_alias_value(self.Consts.ACTIVE_WAN_ID_ALIAS,
                             self.CacheKeys.ACTIVE_GATEWAY_ID)

        if gwname := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME]:
            return gwname, ip
        else:
            gateways = self.all_gateways()
            try:
                wan_name = [wan for wan, (_, _, wan_id)
                            in gateways.items() if wan_id == id].pop()
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME] = wan_name, 300
                return wan_name, ip
            except IndexError:
                del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME]
                del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]
                del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP]
                return None, ip

    def update_active_gateway(self, wan_name: str | None = None) -> bool:
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

        def set_active_wan_id(new_id: str, wan_name: str) -> bool:
            if not (old_id := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]):
                url = self.__consts.get_alias_url(
                    self.__consts.ACTIVE_WAN_ID_ALIAS)
                r = self.__make_get_request(url)
                old_id = r['rows'][0]['ip']

            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME]
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]
            if set_alias(self.__consts.ACTIVE_WAN_ID_ALIAS, new_id, old_id):
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID] = id, 300
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME] = wan_name, 300
                return True
            return False

        gateways = self.all_gateways()
        if wan_name and wan_name not in gateways:
            return False

        old_wan, old_ip = self.active_gateway()

        # new active WAN name has been provided as parameter
        if wan_name and wan_name != old_wan and wan_name in gateways:
            ip, _, id = gateways[wan_name]
            return set_active_wan(ip, old_ip) and set_active_wan_id(id, wan_name)

        # update current active WAN IP address
        elif old_wan and old_wan in gateways and (ip := gateways[old_wan][0]) != old_ip:
            return set_active_wan(ip, old_ip)

        return False
