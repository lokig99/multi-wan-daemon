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


def get_settings_value(section: str, key: str, env_key: str) -> Any | None:
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


def get_interfaces() -> list[Interface]:
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
    if level := get_settings_value('logging', 'level', 'LOGGING_LEVEL'):
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


class Logging:
    LEVEL = _get_logging_level()


class HealthChecks:
    def __init__(self, url: str, enabled=False) -> None:
        self.url = url
        self.enabled = enabled

    @staticmethod
    def defaults() -> 'HealthChecks':
        enabled = bool(e) if (e := get_settings_value(
            'health', 'enabled', 'HEALTH_ENABLED')) else False
        if not enabled:
            return HealthChecks('', enabled)

        if not (url := get_settings_value('health', 'url', 'HEALTH_URL')):
            missing = (v[1] for v in ((url, 'url'),) if not v[0])
            raise DefaultsMissingException(
                f'HealthChecks config is incomplete, fields missing: {", ".join(missing)}')
        return HealthChecks(url, enabled)
