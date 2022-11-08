import requests
from typing import Any

import config as cfg


class OpnSenseClient:
    def __init__(self, host: str) -> None:
        self.host = host

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

    def all_gateways(self) -> dict[str, tuple[str, int]]:
        url = cfg.OpnSense.INTERFACE_CONFING_URL.format(host=self.host)
        response = self.__make_get_request(url)
        rdict = response.json()
        gateways: dict[str, tuple[str, int]] = {}
        for wan, priority in cfg.OpnSense.WANS.items():
            if wan in rdict:
                gateways[wan] = rdict[wan]['ipv4'][0]['ipaddr'], priority
        return gateways

    def active_gateway(self) -> tuple[str | None, str]:
        url = cfg.OpnSense.GET_ACTIVE_WAN_URL.format(host=self.host)
        response = self.__make_get_request(url)
        rdict = response.json()
        ip = rdict['rows'][0]['ip']
        gateways = self.all_gateways()
        try:
            wan_name = [wan for wan,
                        (wan_ip, _) in gateways.items() if wan_ip == ip].pop()
            return wan_name, ip
        except IndexError as error:
            print(error)
        return None, ip

    def update_active_gateway(self, wan_name: str | None = None) -> bool:
        def set_active_wan(new_ip: str, old_ip: str):
            # delete old entry
            url = cfg.OpnSense.DELETE_ACTIVE_WAN_URL.format(host=self.host)
            r = self.__make_post_request(url, {'address': old_ip})
            if r.json()['status'] == 'failed':
                return False

            # add new entry
            url = cfg.OpnSense.ADD_ACTIVE_WAN_URL.format(host=self.host)
            r = self.__make_post_request(url, {'address': new_ip})
            if r.json()['status'] == 'failed':
                return False

            return True

        gateways = self.all_gateways()
        if wan_name and wan_name not in gateways:
            return False

        old_wan, old_ip = self.active_gateway()

        # new active WAN name has been provided as parameter
        if wan_name and wan_name != old_wan:
            ip, _ = gateways[wan_name]
            return set_active_wan(ip, old_ip)
        # update current active WAN IP address
        elif old_wan and (ip := gateways[old_wan][0]) != old_ip:
            return set_active_wan(ip, old_ip)

        return False


class GandiClient:
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
        url = cfg.Gandi.MAIN_RECORD_URL
        response = self.__make_get_request(url)
        rdict = response.json()
        return rdict['rrset_values'][0]

    def set_domain_ip(self, ip: str):
        url = cfg.Gandi.MAIN_RECORD_URL
        record = {
            'rrset_type': 'A',
            'rrset_values': [ip],
            'rrset_ttl': 300
        }
        response = self.__make_put_request(url, record)
        return response.json()['message'] == 'DNS Record Created'


def main():
    opnclient = OpnSenseClient(cfg.OpnSense.HOST)
    gandiclient = GandiClient()

    opnclient.update_active_gateway()
    current_gateway, current_ip = opnclient.active_gateway()
    available_gateways = opnclient.all_gateways()

    priority_gateway, (priority_ip, _) = min(available_gateways.items(),
                                             key=lambda item: item[1][1])

    # gateway is alive
    if current_gateway:
        # check if gateway with higher priority is available
        if priority_gateway != current_gateway:
            opnclient.update_active_gateway(priority_gateway)
            current_gateway, current_ip = priority_gateway, priority_ip

        # check if public IP changed
        domain_ip = gandiclient.domain_ip()
        if current_ip != domain_ip:
            gandiclient.set_domain_ip(current_ip)

    # gateway is dead -> replace with available gateway with the highest priority 
    else:
        opnclient.update_active_gateway(priority_gateway)

        gandiclient.set_domain_ip(priority_ip)


if __name__ == '__main__':
    main()
