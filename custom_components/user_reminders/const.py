from datetime import timedelta
import logging

DOMAIN = "user_reminders"
EVENT_REMINDER_DUE = "user_reminder_due"
CONF_REMINDER_LIST_NAME = "user_reminder_list_name"
CONF_IGNORED_USERS = "ignored_users"
LOGGER = logging.getLogger(__package__)
STORE_VERSION = 1
STORE_KEY = "reminders"

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
