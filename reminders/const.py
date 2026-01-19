from dataclasses import dataclass
from enum import IntFlag, StrEnum
import logging
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

DOMAIN = "reminders"
LOGGER = logging.getLogger(__package__)


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


class ReminderItemFactory:
    """Simple wrapper for our todo items."""

    def __init__(
        self,
        uid: str | None = None,
        list_id: str | None = None,
        summary: str | None = None,
        due: date | datetime | None = None,
    ):
        self.uid = uid
        self.list_id = list_id
        self.summary = summary
        self.due = due

    @staticmethod
    def normalize_date(
        due_date: str | datetime | date | None, uid: str
    ) -> datetime | None:
        if isinstance(due_date, str):
            try:
                due_date = datetime.fromisoformat(due_date)
            except (ValueError, TypeError):
                LOGGER.error(
                    f"Couldn't load item {uid} due to bad date format {due_date}"
                )
                pass

        if isinstance(due_date, datetime):
            return due_date
        elif isinstance(due_date, date):
            return datetime.combine(due_date, time(hour=9, minute=0, second=0))
        elif due_date is None:
            return datetime.now() + timedelta(days=1)
        else:
            LOGGER.error(f"Couldn't load item {uid} due to unknown type of {due_date}")
            return None

    def build(self, ctx_uid):
        uid = self.uid or str(uuid4()).replace("-", "")
        due_date = self.normalize_date(self.due, uid)
        if self.list_id is None:
            raise ValueError("Can't create a ReminderItem with no list_id")
        if due_date == None:
            due_date = datetime.now() + timedelta(days=1)
            due_date = datetime.combine(due_date, time(hour=9, minute=0, second=0))
        if isinstance(due_date, date) and not isinstance(due_date, datetime):
            due_date = datetime.combine(due_date, time(hour=9, minute=0, second=0))

        return ReminderItem(uid, self.list_id, self.summary, due_date, ctx_uid, None)


@dataclass
class ReminderItem:
    """Simple wrapper for our todo items."""

    def __init__(
        self,
        uid: str,
        list_id: str,
        summary,
        due: datetime,
        user_id: str | None,
        last_fired: datetime | None,
    ):
        self.uid = uid
        self.list_id = list_id
        self.summary = summary
        self.due = due
        self.user_id = user_id
        self.last_fired = last_fired
