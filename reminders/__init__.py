import dataclasses
from typing import Any, Callable, Iterable, Sequence, final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    SupportsResponse,
    HomeAssistant,
    ServiceCall,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util.hass_dict import HassKey
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util.json import JsonValueType
from propcache.api import cached_property

from .const import (
    DOMAIN,
    LOGGER,
    SERVICE_ADD_SCHEMA,
    SERVICE_REMOVE_SCHEMA,
    SERVICE_GET_ITEMS_SCHEMA,
    SERVICE_UPDATE_SCHEMA,
    ReminderItem,
    ReminderItemFactory,
    ReminderListEntityFeature,
    ReminderServices,
)

DATA_COMPONENT: HassKey[EntityComponent["ReminderListEntity"]] = HassKey(DOMAIN)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Reminders core domain."""
    LOGGER.debug("Setting up Reminder integration")

    hass.data[DATA_COMPONENT] = EntityComponent(LOGGER, DOMAIN, hass)  # type: ignore
    component = hass.data[DATA_COMPONENT]

    component.async_register_entity_service(
        ReminderServices.ADD_ITEM,
        cv.make_entity_service_schema(SERVICE_ADD_SCHEMA),
        _async_add_reminder_item,
        required_features=[ReminderListEntityFeature.CREATE_REMINDER_ITEM],
    )
    component.async_register_entity_service(
        ReminderServices.UPDATE_ITEM,
        cv.make_entity_service_schema(SERVICE_UPDATE_SCHEMA),
        _async_update_reminder_item,
        required_features=[ReminderListEntityFeature.UPDATE_REMINDER_ITEM],
    )
    component.async_register_entity_service(
        ReminderServices.REMOVE_ITEM,
        cv.make_entity_service_schema(SERVICE_REMOVE_SCHEMA),
        _async_remove_reminder_items,
        required_features=[ReminderListEntityFeature.REMOVE_REMINDER_ITEM],
    )
    component.async_register_entity_service(
        ReminderServices.GET_ITEMS,
        cv.make_entity_service_schema(SERVICE_GET_ITEMS_SCHEMA),
        _async_get_reminder_items,
        supports_response=SupportsResponse.ONLY,
    )

    await component.async_setup(config)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    return await hass.data[DATA_COMPONENT].async_setup_entry(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.data[DATA_COMPONENT].async_unload_entry(entry)


CACHED_PROPERTIES_WITH_ATTR_ = {
    "reminder_items",
}


class ReminderListEntity(Entity, cached_properties=CACHED_PROPERTIES_WITH_ATTR_):
    _attr_reminder_items: list[ReminderItem] | None = None
    _update_listeners: list[Callable[[list[JsonValueType] | None], None]] | None = None

    @property
    def state(self) -> int | None: # type: ignore
        LOGGER.debug(f"updating reminder list entity state")
        return len(self.reminder_items or [])

    @cached_property
    def reminder_items(self) -> list[ReminderItem] | None:
        return self._attr_reminder_items

    async def async_create_reminder_item(
        self, call: ServiceCall, item: ReminderItemFactory
    ) -> None:
        raise NotImplementedError

    async def async_update_reminder_item(
        self, call: ServiceCall, item: ReminderItem
    ) -> None:
        raise NotImplementedError

    async def async_remove_reminder_items(
        self, call: ServiceCall, uids: list[str]
    ) -> None:
        raise NotImplementedError

    async def async_get_reminder_items(
        self, call: ServiceCall, uids: list[str] | None
    ) -> Sequence[ReminderItem]:
        raise NotImplementedError

    @final
    @callback
    def async_subscribe_updates(
        self,
        listener: Callable[[list[JsonValueType] | None], None],
    ) -> CALLBACK_TYPE:
        """Subscribe to Reminder list item updates.

        Called by websocket API.
        """
        if self._update_listeners is None:
            self._update_listeners = []
        self._update_listeners.append(listener)

        @callback
        def unsubscribe() -> None:
            if self._update_listeners:
                self._update_listeners.remove(listener)

        return unsubscribe

    @final
    @callback
    def async_update_listeners(self) -> None:
        """Push updated Reminder items to all listeners."""
        if not self._update_listeners:
            return

        reminder_items: list[JsonValueType] = [
            dataclasses.asdict(item) for item in self._attr_reminder_items or ()
        ]
        for listener in self._update_listeners:
            listener(reminder_items)

    @callback
    def _async_write_ha_state(self) -> None:
        """Notify Reminder item subscribers."""
        super()._async_write_ha_state()
        self.async_update_listeners()


def _api_items_factory(item: ReminderItem) -> dict[str, str]:
    """Convert CalendarEvent dataclass items to dictionary of attributes."""
    return {
        "id": item.uid,
        "summary": item.summary,
        "due": item.due.isoformat(),
        "user_id": item.user_id or "",
        "last_fired": item.last_fired.isoformat() if item.last_fired else "",
    }


async def _async_add_reminder_item(
    entity: ReminderListEntity, call: ServiceCall
) -> None:
    """Add an item to the Reminder list."""
    await entity.async_create_reminder_item(
        call=call,
        item=ReminderItemFactory(
            summary=call.data["summary"],
            due=call.data.get("due", None),
        ),
    )


async def _async_update_reminder_item(
    entity: ReminderListEntity, call: ServiceCall
) -> None:
    """Add an item to the Reminder list."""
    await entity.async_update_reminder_item(
        call=call,
        item=ReminderItem(
            uid=call.data["uid"],
            summary=call.data["summary"],
            due=call.data["due"],
            list_id="",
            user_id=None,
            last_fired=call.data.get("last_fired", None),
        ),
    )


async def _async_remove_reminder_items(
    entity: ReminderListEntity, call: ServiceCall
) -> None:
    """Add an item to the Reminder list."""
    await entity.async_remove_reminder_items(
        call=call,
        uids=call.data["uids"],
    )


async def _async_get_reminder_items(
    entity: ReminderListEntity, call: ServiceCall
) -> dict[str, list[dict[str, str]]]:
    """Add an item to the Reminder list."""
    current_reminder_items = await entity.async_get_reminder_items(
        call=call, uids=call.data.get("uids", None)
    )
    items = [_api_items_factory(item) for item in current_reminder_items or ()]
    return {"reminders": items}
