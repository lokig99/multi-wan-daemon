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
    """
    The main daemon function that runs periodically.
    It checks if the current gateway is alive and if not, it replaces it with the gateway with the highest priority.
    It also checks if the public IP changed and updates the DNS record if necessary.

    Supports HealthChecks.io service.

    Args:
    -----
        `opnclient` (OpnSenseClient): The OpnSense client instance that handles gateways on the router.
        `gandiclient` (GandiClient): The Gandi client instance that handles DNS records.
        `healthchecks_config` (HealthChecks): The configuration for the HealthChecks.io service.
    """
    log.info("Starting new daemon job...")
    if healthchecks_config.enabled:
        requests.get(f'{healthchecks_config.url}/start', timeout=10)
    start_time = time.time()

    opnclient.update_active_gateway()
    current_gateway = opnclient.active_gateway()
    available_gateways = opnclient.all_gateways()

    if not available_gateways:
        log.error("No gateways available!")
        return

    _, priority_gateway = min(available_gateways.items(),
                              key=lambda item: item[1].priority)
    log.info(f'Available gateways: {available_gateways}')
    log.info(f'Current gateway: {current_gateway.name} --- {current_gateway.ip}')
    log.info(f'Priority gateway: {priority_gateway.name} --- {priority_gateway.ip}')

    # gateway is alive
    if current_gateway.name in available_gateways:
        log.info(f'Current gateway is ALIVE ({current_gateway.name})')
        # check if gateway with higher priority is available
        if priority_gateway.name != current_gateway.name:
            log.info(
                f'Gateway with higher priority is available ({priority_gateway.name})')
            opnclient.update_active_gateway(priority_gateway.name)
            current_gateway = priority_gateway

        # check if public IP changed
        domain_ip = gandiclient.domain_ip()
        if current_gateway.ip != domain_ip:
            log.warning(
                f'External public IP changed - updating DNS record ({domain_ip} -> {current_gateway.ip})')
            gandiclient.set_domain_ip(current_gateway.ip)

    # gateway is dead -> replace with available gateway with the highest priority
    else:
        log.error(f'Current gateway is DEAD ({current_gateway.name})')
        log.info(
            f'Replacing dead gateway ({current_gateway.name}) with: {priority_gateway.name}')
        opnclient.update_active_gateway(priority_gateway.name)
        log.info(
            f'Gateway changed - updating DNS record to: {priority_gateway.name}')
        gandiclient.set_domain_ip(priority_gateway.ip)

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
