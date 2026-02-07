import logging
from datetime import timedelta
from enum import IntFlag, StrEnum

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

DOMAIN = "reminders"
LOGGER = logging.getLogger(__package__)

EVENT_REMINDER_DUE = "user_reminder_due"
CONF_REMINDER_LIST_NAME = "user_reminder_list_name"
CONF_IGNORED_USERS = "ignored_users"
STORE_VERSION = 1
STORE_KEY = "reminders"
ENTITY_FORMAT = "user_reminders_{}"

SETUP_INTERVAL = timedelta(minutes=1)

# Frontend constants
INTEGRATION_VERSION = "1.0.4"
URL_BASE = "/user_reminders"
CARD_FILENAME = "reminder-card.js"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}"

JSMODULES = [
    {
        "url": CARD_URL,
        "version": INTEGRATION_VERSION,
    }
]


class ReminderServices(StrEnum):
    """Services for the Reminder integration."""

    ADD_ITEM = "add_item"
    UPDATE_ITEM = "update_item"
    GET_ITEMS = "get_items"
    REMOVE_ITEM = "remove_item"


class ReminderListEntityFeature(IntFlag):
    """Supported features of the Reminder List entity."""

    CREATE_REMINDER_ITEM = 2**0
    REMOVE_REMINDER_ITEM = 2**1
    UPDATE_REMINDER_ITEM = 2**2
    GET_REMINDER_ITEM_LIST = 2**3


SERVICE_ADD_SCHEMA = {
    vol.Required("summary"): cv.string,
    vol.Optional("due"): cv.datetime,
    vol.Optional("user"): str,
}
SERVICE_UPDATE_SCHEMA = {
    vol.Required("uid"): cv.uuid4_hex,
    vol.Required("summary"): cv.string,
    vol.Required("due"): cv.datetime,
    vol.Optional("last_fired"): cv.datetime,
}
SERVICE_REMOVE_SCHEMA = {
    vol.Required("uids"): vol.All(cv.ensure_list, [cv.uuid4_hex]),
}
SERVICE_GET_ITEMS_SCHEMA = {
    vol.Optional("uids"): vol.All(cv.ensure_list, [cv.uuid4_hex]),
}
