from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.util.hass_dict import HassKey

from .const import (
    CONF_IGNORED_USERS,
    DOMAIN,
    LOGGER,
    SERVICE_ADD_SCHEMA,
    SERVICE_GET_ITEMS_SCHEMA,
    SERVICE_REMOVE_SCHEMA,
    SERVICE_UPDATE_SCHEMA,
    ReminderListEntityFeature,
    ReminderServices,
)
from .intents import async_setup_intents
from .reminder_item import ReminderItem, ReminderItemFactory
from .reminder_entity import ReminderListEntity
from .scheduler import Scheduler
from .storage import ReminderStore

type UserReminderConfigEntry = ConfigEntry[ReminderStore]


@dataclass
class ReminderDomainData:
    """Data stored in hass.data for the reminder domain."""

    component: EntityComponent[ReminderListEntity]
    store: ReminderStore | None = None
    scheduler: Scheduler | None = None
    reminders: dict[str, dict] | None = None


DATA_REMINDER: HassKey[ReminderDomainData] = HassKey(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Reminders core domain."""
    LOGGER.debug("Setting up Reminder integration")

    component = EntityComponent[ReminderListEntity](LOGGER, DOMAIN, hass)

    # Initialize domain data
    hass.data[DATA_REMINDER] = ReminderDomainData(component=component)

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

    # Set up intent handlers (only once per domain)
    await async_setup_intents(hass)

    await component.async_setup(config)
    return True


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


async def register_frontend_resources(hass: HomeAssistant):
    from .frontend import async_register_frontend

    await async_register_frontend(hass)


async def async_setup_entry(
    hass: HomeAssistant, entry: UserReminderConfigEntry
) -> bool:
    await register_frontend_resources(hass)

    store = ReminderStore(hass)
    scheduler = Scheduler()

    reminders_data = await store.async_load() or {}

    entry.runtime_data = store

    domain_data = hass.data[DATA_REMINDER]
    domain_data.store = store
    domain_data.reminders = reminders_data
    domain_data.scheduler = scheduler
    scheduler = scheduler.start_scheduler(hass)

    ignored_users = entry.data.get(CONF_IGNORED_USERS, [])
    users = await hass.auth.async_get_users()
    entities = []

    component = domain_data.component

    current_entities_list = []
    for e in component.entities:
        current_entities_list.append(e.unique_id)

    for user in users:
        if user.system_generated or not user.name or user.id in ignored_users:
            continue

        entity = ReminderListEntity(hass, user.id, user.name)
        if entity.unique_id in current_entities_list:
            continue

        LOGGER.info(
            f"Creating reminder entity for user: {user.name} {entity.unique_id}"
        )
        entities.append(entity)

    await component.async_add_entities(entities)

    await hass.config_entries.async_forward_entry_setups(entry, [])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data[DATA_REMINDER]
    if domain_data.scheduler:
        await domain_data.scheduler.stop_scheduler()
        domain_data.scheduler = None
    return True
