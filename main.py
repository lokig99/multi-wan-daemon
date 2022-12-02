import logging as log
import time
from typing import Any

import requests
import schedule

import config as cfg

log.basicConfig(level=cfg.Logging.LEVEL,
                format='%(asctime)s %(levelname)s: %(message)s')


class Cache:
    """
    Add new key/value: 
        cache[key] = value, timeout_seconds
        >>> cache = Cache()
        >>> cache['k1'] = 'value', 5

    Get value: 
        cache[key] -> returns value

    Delete key/value: 
        del cache[key]
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


class OpnSenseClient:
    class Consts:
        __INTERFACE_CONFING_URL__ = '{protocol}://{host}/api/diagnostics/interface/getInterfaceConfig'
        ACTIVE_WAN_ALIAS = 'Active_WAN'
        ACTIVE_WAN_ID_ALIAS = 'Active_WAN_Id'
        __GET_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/list/{alias}'
        __ADD_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/add/{alias}'
        __DELETE_ALIAS_URL__ = '{protocol}://{host}/api/firewall/alias_util/delete/{alias}'

        def __init__(self, host: str, use_https: bool) -> None:
            self.__host = host
            self.__protocol = 'https' if use_https else 'http'
            self.INTERFACE_CONFING_URL = self.__INTERFACE_CONFING_URL__.format(
                protocol=self.__protocol, host=host)

        def get_alias_url(self, alias: str) -> str:
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

    def __init__(self, config: cfg.OpnSenseConfig) -> None:
        self.__host = config.host
        self.__wans = config.wans[:]
        self.__key = config.key
        self.__secret = config.secret
        self.__cache = Cache()
        self.__consts = self.Consts(self.__host, config.use_https)
        self.__timeout = config.timeout

    @staticmethod
    def with_default_config() -> 'OpnSenseClient':
        return OpnSenseClient(cfg.OpnSenseConfig.defaults())

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


class GandiClient:
    class Consts:
        __MAIN_RECORD_URL__ = 'https://api.gandi.net/v5/livedns/domains/{domain}/records/%40/A'

        def __init__(self, domain: str) -> None:
            self.MAIN_RECORD_URL = self.__MAIN_RECORD_URL__.format(
                domain=domain)

    class CacheKeys:
        DOMAIN_IP = 'domip'

    def __init__(self, config: cfg.GandiConfig) -> None:
        self.__domain = config.domain
        self.__apikey = config.apikey
        self.__cache = Cache()
        self.__consts = self.Consts(self.__domain)

    @staticmethod
    def with_default_config() -> 'GandiClient':
        return GandiClient(cfg.GandiConfig.defaults())

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


def daemon(opnclient: OpnSenseClient, gandiclient: GandiClient, healthchecks_config: cfg.HealthChecks):
    log.info("Starting new daemon job...")
    if healthchecks_config.enabled:
        requests.get(f'{healthchecks_config.url}/start', timeout=10)
    start_time = time.time()
    
    opnclient.update_active_gateway()
    current_gateway, current_ip = opnclient.active_gateway()
    available_gateways = opnclient.all_gateways()

    if not available_gateways:
        log.error("No gateways available!")
        return

    priority_gateway, (priority_ip, _, _) = min(available_gateways.items(),
                                                key=lambda item: item[1][1])
    log.info(f'Available gateways: {available_gateways}')
    log.info(f'Current gateway: {current_gateway} --- {current_ip}')
    log.info(f'Priority gateway: {priority_gateway} --- {priority_ip}')

    # gateway is alive
    if current_gateway in available_gateways:
        log.info(f'Current gateway is ALIVE ({current_gateway})')
        # check if gateway with higher priority is available
        if priority_gateway != current_gateway:
            log.info(
                f'Gateway with higher priority is available ({priority_gateway})')
            opnclient.update_active_gateway(priority_gateway)
            current_gateway, current_ip = priority_gateway, priority_ip

        # check if public IP changed
        domain_ip = gandiclient.domain_ip()
        if current_ip != domain_ip:
            log.warning(
                f'External public IP changed - updating DNS record ({domain_ip} -> {current_ip})')
            gandiclient.set_domain_ip(current_ip)

    # gateway is dead -> replace with available gateway with the highest priority
    else:
        log.error(f'Current gateway is DEAD ({current_gateway})')
        log.info(
            f'Replacing dead gateway ({current_gateway}) with: {priority_gateway}')
        opnclient.update_active_gateway(priority_gateway)
        log.info(f'Gateway changed - updating DNS record to: {priority_ip}')
        gandiclient.set_domain_ip(priority_ip)

    end_time = time.time()
    if healthchecks_config.enabled:
        requests.get(healthchecks_config.url, timeout=10)
    log.info(
        f'Daemon job finished succesfully in {round(end_time - start_time, 3)} seconds')


def main():
    def job(opnclient: OpnSenseClient, gandiclient: GandiClient, healthchecks_config: cfg.HealthChecks):
        try:
            daemon(opnclient, gandiclient, healthchecks_config)
        except Exception as e:
            log.error('Exception occured while executing daemon job', exc_info=e)

    try:
        opnclient = OpnSenseClient.with_default_config()
        gandiclient = GandiClient.with_default_config()
        healthchecks_config = cfg.HealthChecks.defaults()
        schedule.every(10).seconds.do(
            job, opnclient=opnclient, gandiclient=gandiclient, healthchecks_config=healthchecks_config)
    except cfg.DefaultsMissingException as e:
        log.error('Exception occured while configuring clients', exc_info=e)
        import sys
        sys.exit(1)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
