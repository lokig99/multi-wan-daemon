import json
import os
import re
from dataclasses import dataclass
from logging import DEBUG, ERROR, INFO, WARNING
from typing import Any

__ROOT_DIR__ = os.path.abspath(os.path.dirname(__file__))
__CONFIG_DIR__ = cfgdir if ('CONFIG_DIRECTORY' in os.environ and (
    cfgdir := os.environ['CONFIG_DIRECTORY'])) else __ROOT_DIR__

__SETTINGS_FILE__ = os.path.join(__CONFIG_DIR__, 'settings.json')
__INTERFACES_FILE__ = os.path.join(__CONFIG_DIR__, 'interfaces.json')


@dataclass
class Interface:
    name: str
    id: str
    priority: int


def _get_settings_value(section: str, key: str, env_key: str) -> Any | None:
    value = None
    if os.path.exists(__SETTINGS_FILE__):
        with open(__SETTINGS_FILE__, 'rt') as f:
            settings = json.load(f)
            if section in settings and key in settings[section]:
                value = settings[section][key]
    else:
        # get value from environment
        value = v if (env_key in os.environ and (
            v := os.environ[env_key])) else None
    return value


def _get_interfaces() -> list[Interface]:
    interfaces: list[Interface] = []

    if os.path.exists(__INTERFACES_FILE__):
        with open(__INTERFACES_FILE__, 'rt', encoding='utf8') as f:
            wans: list[dict[str, Any]] = json.load(f)
            for wan in wans:
                interfaces.append(
                    Interface(wan['name'], wan['id'], wan['priority']))
            del wans
        return interfaces

    # get interfaces from environment
    for x in range(256):
        wan_envkey = f'OPNSENSE_WAN_{x}'
        if wan_envkey in os.environ:
            match = re.search(
                r"^(\w*)\s*,\s*(((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4})\s*,\s*(\d+)$", os.environ[wan_envkey])
            if match:
                groups = match.groups()
                interfaces.append(
                    Interface(groups[0], groups[1], int(groups[-1])))
    return interfaces


def _get_logging_level() -> int:
    if level := _get_settings_value('logging', 'level', 'LOGGING_LEVEL'):
        match level.lower():
            case 'debug':
                return DEBUG
            case 'info':
                return INFO
            case 'error':
                return ERROR
            case 'warning' | 'warn':
                return WARNING
    return DEBUG


class DefaultsMissingException(Exception):
    pass


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
        host = _get_settings_value('opnsense', 'host', 'OPNSENSE_HOST')
        key = _get_settings_value('opnsense', 'key', 'OPNSENSE_KEY')
        secret = _get_settings_value('opnsense', 'secret', 'OPNSENSE_SECRET')
        timeout = int(t) if (t := _get_settings_value(
            'opnsense', 'timeout', 'OPNSENSE_TIMEOUT')) else OpnSenseConfig.__DEFAULT_TIMEOUT__ 
        use_https = https if (https := _get_settings_value(
            'opnsense', 'use_https', 'OPNSENSE_USE_HTTPS')) else True
        wans: list[Interface] = _get_interfaces()
        if not host or not key or not secret or not wans:
            missing = (v[1] for v in ((host, 'host'), (key, 'key'),
                       (secret, 'secret'), (wans, 'interfaces (wans)')) if not v[0])
            raise DefaultsMissingException(
                f'OPNsense config is incomplete, fields missing: {", ".join(missing)}')
        return OpnSenseConfig(host, key, secret, wans, use_https, timeout)


class GandiConfig:
    def __init__(self, domain: str, apikey: str) -> None:
        self.apikey = apikey
        self.domain = domain

    @staticmethod
    def defaults() -> 'GandiConfig':
        api_key = _get_settings_value('gandi', 'apikey', 'GANDI_API_KEY')
        domain = _get_settings_value('gandi', 'domain', 'GANDI_DOMAIN')
        if not api_key or not domain:
            missing = (v[1] for v in ((api_key, 'apikey'),
                       (domain, 'domain')) if not v[0])
            raise DefaultsMissingException(
                f'Gandi.net config is incomplete, fields missing: {", ".join(missing)}')
        return GandiConfig(domain, api_key)


class Logging:
    LEVEL = _get_logging_level()
