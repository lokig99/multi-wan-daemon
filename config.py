import json
import os
import re
from dataclasses import dataclass
from logging import DEBUG, ERROR, INFO, WARNING
from typing import Any

__ROOT_DIR__ = os.path.abspath(os.path.dirname(__file__))
"""The absolute path of the root directory of the application."""
__CONFIG_DIR__ = cfgdir if ('CONFIG_DIRECTORY' in os.environ and (
    cfgdir := os.environ['CONFIG_DIRECTORY'])) else __ROOT_DIR__
"""The configuration directory of the application.
If the environment variable `CONFIG_DIRECTORY` is set then it will be used, otherwise the root directory will be used."""
__SETTINGS_FILE__ = os.path.join(__CONFIG_DIR__, 'settings.json')
"""The absolute path to the settings JSON file."""
__INTERFACES_FILE__ = os.path.join(__CONFIG_DIR__, 'interfaces.json')
"""The absolute path to the interfaces JSON file."""


@dataclass
class Interface:
    """
    Represents a WAN interface in OPNsense with a name, IP address and priority
    """
    name: str
    """The name of the interface in OPNsense, for example: `wan1`"""
    id: str
    """The ID of the interface in OPNsense, for example: `1.0.0.0`"""
    priority: int
    """The priority of the interface in OPNsense, for example: `1`. 
    
    The lower the number, the higher the priority"""


def get_settings_value(section: str, key: str, env_key: str) -> Any | None:
    """
    Get a value from the settings file or from the environment.

    Parameters:
    ----------
        `section` (str): The section of the settings file to get the value from.
        `key` (str): The key from section of the settings file to get the value from.
        `env_key` (str): The name of the environment variable to get the value from.
    Returns:
    --------
        `Any` | `None` - The value from the settings file or from the environment or `None` if the value was not found.
    """
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
    """
    Get the WAN interfaces from the interfaces JSON file or from the environment if the file does not exist. If the file does exist then environment variables will be ignored.

    If the environmental variables are used it will look for the following variables:
    - `OPNSENSE_WAN_{x}`: The name, ID and priority of the WAN interface in a form of a comma separated string, for example: `wan1, 1.0.0.0, 1`.
    The `{x}` is a number from 0 to 255.

    Returns:
    --------
        `list[Interface]` - The list of WAN interfaces in a form of `Interface` objects.
    """
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
    """
    Get the logging level from the settings file or from the environment if the file does not exist. If the file does exist then environment variables will be ignored.

    If the environmental variables are used it will look for the following variables:
    - `LOGGING_LEVEL`: The logging level, for example: `DEBUG`.

    Returns:
    --------
        `int` - The logging level.
    """
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
    """
    The exception that is thrown when a required default value is missing.
    """
    pass


class InvalidConfigException(Exception):
    """
    The exception that is thrown when the configuration is invalid.
    """
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


class Logging:
    """
    The Logging configuration class.
    """
    LEVEL = _get_logging_level()


class HealthChecks:
    """
    The HealthChecks configuration class for the healtchecks.io service.

    Determines if the health checks are enabled and sets the base URL for the health checks.
    """

    def __init__(self, url: str, enabled=False) -> None:
        self.url = url
        """The base URL for the health check endpoint."""
        self.enabled = enabled
        """Whether the health checks are enabled or not."""

    @staticmethod
    def defaults() -> 'HealthChecks':
        """
        Get the default values for the health checks from the settings file or from the environment if the file does not exist. If the file does exist then environment variables will be ignored.

        Raises:
        -------
            `DefaultsMissingException`: If the required default values are missing.
            `InvalidConfigException`: If the `health.enabled` value is not `true` or `false`.

        Returns:
        --------
            `HealthChecks` - The default values for the healthchecks.io service.
        """
        url = get_settings_value('health', 'url', 'HEALTH_URL')
        value = get_settings_value('health', 'enabled', 'HEALTH_ENABLED')
        if value.lower() == 'true':
            enabled = True
        elif value.lower() == 'false':
            enabled = False
        else:
            raise InvalidConfigException(
                f'invalid value for health.enabled, must be "true" or "false" but was: "{value}"')
            
        if enabled and not url:
            missing = (v[1] for v in ((url, 'url'),) if not v[0])
            raise DefaultsMissingException(
                f'HealthChecks config is incomplete, fields missing: {", ".join(missing)}')
        return HealthChecks(url, enabled)
