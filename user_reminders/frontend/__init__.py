"""Frontend resource registration for User Reminders."""

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
)

from ..const import DOMAIN, INTEGRATION_VERSION, URL_BASE, JSMODULES

_LOGGER = logging.getLogger(__name__)


class JSModuleRegistration:
    """Handle JS module registration for custom cards."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the registration handler."""
        self.hass = hass
        self._registered = False

    async def _register_static_path(self) -> None:
        """Register the static path for frontend files."""
        frontend_path = Path(__file__).parent
        await self.hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    url_path=URL_BASE,
                    path=str(frontend_path),
                    cache_headers=False,
                )
            ]
        )
        _LOGGER.debug(f"Registered static path: {URL_BASE} -> {frontend_path}")

    def _schedule_lovelace_registration(self) -> None:
        """Schedule lovelace resource registration when Home Assistant is ready."""
        if self.hass.is_running:
            self.hass.async_create_task(self._register_lovelace_resources())
        else:
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_on_ha_started
            )

    @callback
    async def _async_on_ha_started(self, _event) -> None:
        """Register lovelace resources after Home Assistant starts."""
        await self._register_lovelace_resources()

    async def _register_lovelace_resources(self) -> None:
        """Register reminders card as a lovelace resource."""
        try:

            lovelace_config = self.hass.data.get("lovelace")
            if not lovelace_config:
                _LOGGER.warning("Lovelace not loaded, skipping resource registration")
                return

            resources: ResourceStorageCollection = lovelace_config.resources
            if not resources:
                _LOGGER.warning("Lovelace resources not found")
                return

            await self._update_or_create_lovelace_resources(resources)

        except Exception as err:
            _LOGGER.error(
                f"Failed to register lovelace resources: {err}", exc_info=True
            )

    async def _update_or_create_lovelace_resources(
        self, resources: ResourceStorageCollection
    ) -> None:
        for module in JSMODULES:
            versioned_url = f"{module['url']}?v={module['version']}"

            existing = [
                r
                for r in resources.async_items()
                if r.get("url", "").startswith(module["url"])
            ]

            if existing:
                await self._update_existing_resource(resources, existing, versioned_url)
            else:
                await self._create_new_resource(resources, versioned_url)

    async def _update_existing_resource(
        self, resources: "ResourceStorageCollection", existing: list, versioned_url: str
    ) -> None:
        for resource in existing:
            await resources.async_update_item(
                resource["id"],
                {"url": versioned_url, "res_type": "module"},
            )
        _LOGGER.debug(f"Updated resource: {versioned_url}")

    async def _create_new_resource(
        self, resources: ResourceStorageCollection, versioned_url: str
    ) -> None:
        await resources.async_create_item({"url": versioned_url, "res_type": "module"})
        _LOGGER.info(f"Registered new resource: {versioned_url}")

    async def async_register(self) -> None:
        if self._registered:
            return

        await self._register_static_path()
        self._schedule_lovelace_registration()
        self._registered = True


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register frontend resources."""
    registration = JSModuleRegistration(hass)
    await registration.async_register()
