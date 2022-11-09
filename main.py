import time
import logging as log
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
        >>> cache['k1'] = 'value', 5

    Get value: 
        cache[key] -> returns value

    Delete key/value: 
        del cache[key]
    """

    def __init__(self) -> None:
        self.__store: dict[str, tuple[Any, float]] = {}

    def __contains__(self, key: str) -> bool:
        return key in self.__store

    def __getitem__(self, key: str) -> None | Any:
        if key in self.__store:
            value, expiration_time = self.__store[key]
            now = time.time()
            if now < expiration_time:
                return value
            # value expired
            del self.__store[key]
        return None

    def __delitem__(self, key: str):
        if key in self.__store:
            del self.__store[key]

    def __setitem__(self, key: str, value: tuple[Any, float]):
        item, timeout = value
        expiration_time = time.time() + timeout
        self.__store[key] = item, expiration_time


class OpnSenseClient:
    class CacheKeys:
        ALL_GATEWAYS = 'allactgw'
        ACTIVE_GATEWAY_ID = 'actgwid'
        ACTIVE_GATEWAY_NAME = 'actgwname'
        ACTIVE_GATEWAY_IP = 'actgwip'

    def __init__(self) -> None:
        self.host = cfg.OpnSense.HOST
        self.__cache = Cache()

    @staticmethod
    def __make_get_request(url: str) -> requests.Response:
        response = requests.get(url,  auth=(
            cfg.OpnSense.KEY, cfg.OpnSense.SECRET))
        response.raise_for_status()
        return response

    @staticmethod
    def __make_post_request(url: str, body: dict[str, Any]) -> requests.Response:
        response = requests.post(url, json=body,  auth=(
            cfg.OpnSense.KEY, cfg.OpnSense.SECRET))
        response.raise_for_status()
        return response

    def all_gateways(self) -> dict[str, tuple[str, int, str]]:
        if not (gateways := self.__cache[self.CacheKeys.ALL_GATEWAYS]):
            url = cfg.OpnSense.INTERFACE_CONFING_URL.format(host=self.host)
            response = self.__make_get_request(url)
            rdict = response.json()
            # gateways: dict[str, tuple[str, int, str]]
            gateways = {}
            for wan, (priority, id) in cfg.OpnSense.WANS.items():
                if wan in rdict and (ipv4 := rdict[wan]['ipv4']):
                    gateways[wan] = ipv4[0]['ipaddr'], priority, id
            self.__cache[self.CacheKeys.ALL_GATEWAYS] = gateways, 5
        return gateways

    def active_gateway(self) -> tuple[str | None, str]:
        # get Active_WAN alias value
        if not (ip := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP]):
            url = cfg.OpnSense.GET_ALIAS_URL.format(
                host=self.host, alias=cfg.OpnSense.ACTIVE_WAN_ALIAS)
            response = self.__make_get_request(url)
            rdict = response.json()
            ip = rdict['rows'][0]['ip']
            self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP] = ip, 300

        # get Active_WAN_Id alias value
        if not (id := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]):
            url = cfg.OpnSense.GET_ALIAS_URL.format(
                host=self.host, alias=cfg.OpnSense.ACTIVE_WAN_ID_ALIAS)
            response = self.__make_get_request(url)
            rdict = response.json()
            id = rdict['rows'][0]['ip']
            self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID] = id, 300

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
            url = cfg.OpnSense.DELETE_ALIAS_URL.format(
                host=self.host, alias=alias)
            r = self.__make_post_request(url, {'address': old_value})
            if r.json()['status'] == 'failed':
                return False

            # add new entry
            url = cfg.OpnSense.ADD_ALIAS_URL.format(
                host=self.host, alias=alias)
            r = self.__make_post_request(url, {'address': new_value})
            if r.json()['status'] == 'failed':
                return False

            return True

        def set_active_wan(new_ip: str, old_ip: str) -> bool:
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP]
            if set_alias(cfg.OpnSense.ACTIVE_WAN_ALIAS, new_ip, old_ip):
                self.__cache[self.CacheKeys.ACTIVE_GATEWAY_IP] = ip, 300
                return True
            return False

        def set_active_wan_id(new_id: str, wan_name: str) -> bool:
            if not (old_id := self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]):
                url = cfg.OpnSense.GET_ALIAS_URL.format(
                    host=self.host, alias=cfg.OpnSense.ACTIVE_WAN_ID_ALIAS)
                rdict = self.__make_get_request(url).json()
                old_id = rdict['rows'][0]['ip']

            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_NAME]
            del self.__cache[self.CacheKeys.ACTIVE_GATEWAY_ID]
            if set_alias(cfg.OpnSense.ACTIVE_WAN_ID_ALIAS, new_id, old_id):
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
        elif old_wan and old_wan in gateways and gateways[old_wan] and (ip := gateways[old_wan][0]) != old_ip:
            return set_active_wan(ip, old_ip)

        return False


class GandiClient:
    class CacheKeys:
        DOMAIN_IP = 'domip'

    def __init__(self) -> None:
        self.__cache = Cache()

    @staticmethod
    def __make_get_request(url: str) -> requests.Response:
        response = requests.get(
            url, headers={'Authorization': f'Apikey {cfg.Gandi.API_KEY}'})
        response.raise_for_status()
        return response

    @staticmethod
    def __make_put_request(url: str, body: dict[str, Any]) -> requests.Response:
        response = requests.put(
            url, headers={'Authorization': f'Apikey {cfg.Gandi.API_KEY}'}, json=body)
        response.raise_for_status()
        return response

    def domain_ip(self) -> str:
        if not (ip := self.__cache[self.CacheKeys.DOMAIN_IP]):
            response = self.__make_get_request(cfg.Gandi.MAIN_RECORD_URL)
            rdict = response.json()
            ip = rdict['rrset_values'][0]
            self.__cache[self.CacheKeys.DOMAIN_IP] = ip, 600
        return ip

    def set_domain_ip(self, ip: str) -> bool:
        record = {
            'rrset_type': 'A',
            'rrset_values': [ip],
            'rrset_ttl': 300
        }
        response = self.__make_put_request(cfg.Gandi.MAIN_RECORD_URL, record)
        success = response.json()['message'] == 'DNS Record Created'
        del self.__cache[self.CacheKeys.DOMAIN_IP]
        if success:
            self.__cache[self.CacheKeys.DOMAIN_IP] = ip, 600
        return success


def daemon(opnclient: OpnSenseClient, gandiclient: GandiClient):
    log.info("Starting new daemon job...")
    start_time = time.time()
    opnclient.update_active_gateway()
    current_gateway, current_ip = opnclient.active_gateway()
    available_gateways = opnclient.all_gateways()

    priority_gateway, (priority_ip, _, _) = min(available_gateways.items(),
                                                key=lambda item: item[1][1])
    log.info(f'Available gateways: {available_gateways}')
    log.info(f'Current gateway: {current_gateway} --- {current_ip}')
    log.info(f'Priority gateway: {priority_gateway} --- { priority_ip}')

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
    log.info(
        f'daemon job finished succesfully in {round(end_time - start_time, 3)} seconds')


def main():
    def job(opnclient: OpnSenseClient, gandiclient: GandiClient):
        try:
            daemon(opnclient, gandiclient)
        except Exception as e:
            log.error('Exception occured while executing daemon job', exc_info=e)

    opnclient = OpnSenseClient()
    gandiclient = GandiClient()

    schedule.every(10).seconds.do(
        job, opnclient=opnclient, gandiclient=gandiclient)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
