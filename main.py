import logging as log
import time

import requests
import schedule

from config import DefaultsMissingException, HealthChecks, Logging
from gandi import GandiClient
from opnsense import OpnSenseClient

log.basicConfig(level=Logging.LEVEL,
                format='%(asctime)s %(levelname)s: %(message)s')


def daemon(opnclient: OpnSenseClient, gandiclient: GandiClient, healthchecks_config: HealthChecks):
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
    def job(opnclient: OpnSenseClient, gandiclient: GandiClient, healthchecks_config: HealthChecks):
        try:
            daemon(opnclient, gandiclient, healthchecks_config)
        except Exception as e:
            log.error('Exception occured while executing daemon job', exc_info=e)

    try:
        opnclient = OpnSenseClient.with_default_config()
        gandiclient = GandiClient.with_default_config()
        healthchecks_config = HealthChecks.defaults()
        schedule.every(10).seconds.do(
            job, opnclient=opnclient, gandiclient=gandiclient, healthchecks_config=healthchecks_config)
    except DefaultsMissingException as e:
        log.error('Exception occured while configuring clients', exc_info=e)
        import sys
        sys.exit(1)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
