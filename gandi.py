from typing import Any

import requests

from cache import Cache
from config import DefaultsMissingException, get_settings_value


class GandiConfig:
    def __init__(self, domain: str, apikey: str) -> None:
        self.apikey = apikey
        self.domain = domain

    @staticmethod
    def defaults() -> 'GandiConfig':
        api_key = get_settings_value('gandi', 'apikey', 'GANDI_API_KEY')
        domain = get_settings_value('gandi', 'domain', 'GANDI_DOMAIN')
        if not api_key or not domain:
            missing = (v[1] for v in ((api_key, 'apikey'),
                       (domain, 'domain')) if not v[0])
            raise DefaultsMissingException(
                f'Gandi.net config is incomplete, fields missing: {", ".join(missing)}')
        return GandiConfig(domain, api_key)


class GandiClient:
    class Consts:
        __MAIN_RECORD_URL__ = 'https://api.gandi.net/v5/livedns/domains/{domain}/records/%40/A'

        def __init__(self, domain: str) -> None:
            self.MAIN_RECORD_URL = self.__MAIN_RECORD_URL__.format(
                domain=domain)

    class CacheKeys:
        DOMAIN_IP = 'domip'

    def __init__(self, config: GandiConfig) -> None:
        self.__domain = config.domain
        self.__apikey = config.apikey
        self.__cache = Cache()
        self.__consts = self.Consts(self.__domain)

    @staticmethod
    def with_default_config() -> 'GandiClient':
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
        if not (ip := self.__cache[self.CacheKeys.DOMAIN_IP]):
            r = self.__make_get_request(self.__consts.MAIN_RECORD_URL)
            ip = r['rrset_values'][0]
            self.__cache[self.CacheKeys.DOMAIN_IP] = ip, 600
        return ip

    def set_domain_ip(self, ip: str) -> bool:
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
