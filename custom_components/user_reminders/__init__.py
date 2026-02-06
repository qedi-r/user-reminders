from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.reminders import DATA_COMPONENT

from .const import CONF_IGNORED_USERS, DOMAIN, LOGGER
from .intents import async_setup_intents
from .reminder_entity import UserRemindersListEntity
from .scheduler import Scheduler
from .storage import ReminderStore

type UserReminderConfigEntry = ConfigEntry[ReminderStore]


async def async_setup_entry(
    hass: HomeAssistant, entry: UserReminderConfigEntry
) -> bool:
    # Register frontend resources
    from .frontend import async_register_frontend

    await async_register_frontend(hass)

    # Set up intent handlers
    await async_setup_intents(hass)

    store = ReminderStore(hass)
    scheduler = Scheduler()

    reminders_data = await store.async_load() or {}

    entry.runtime_data = store

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    hass.data[DOMAIN]["store"] = store
    hass.data[DOMAIN]["reminders"] = reminders_data

    hass.data[DOMAIN]["scheduler"] = scheduler
    scheduler = scheduler.start_scheduler(hass)

    ignored_users = entry.data.get(CONF_IGNORED_USERS, [])
    users = await hass.auth.async_get_users()
    entities = []

    component = hass.data[DATA_COMPONENT]

    current_entities_list = []
    for e in component.entities: #pylint: ignore
        current_entities_list.append(e.unique_id)

    for user in users:
        if user.system_generated or not user.name or user.id in ignored_users:
            continue

        entity = UserRemindersListEntity(hass, user.id, user.name)
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
    scheduler = hass.data[DOMAIN]["scheduler"]
    if scheduler:
        await scheduler.stop_scheduler()
        hass.data[DOMAIN]["scheduler"] = None
    return True
