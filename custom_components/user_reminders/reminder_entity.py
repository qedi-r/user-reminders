from datetime import date, datetime, time, timedelta
from typing import Any, Sequence
from uuid import uuid4

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import Unauthorized, UnknownUser
from homeassistant.helpers.entity import generate_entity_id
from propcache.api import cached_property

from custom_components.reminders import ReminderListEntity
from custom_components.reminders.const import (
    ReminderItem,
    ReminderItemFactory,
    ReminderListEntityFeature,
)

from .const import DOMAIN, LOGGER


async def _get_user_from_call(hass: HomeAssistant, call: ServiceCall):
    user_data = None
    if call.context.user_id:
        user_data = await hass.auth.async_get_user(call.context.user_id)

    if user_data is None:
        LOGGER.warning(f"Unknown user: {call.context.user_id}")
        return None

    return user_data.id


async def _is_automation_driven_user(hass: HomeAssistant, call: ServiceCall):
    event = call.context.origin_event
    user_data = None
    if event and event.event_type == "automation_triggered":
        event_driven_user = call.data.get("user")
        users = await hass.auth.async_get_users()
        for u in users:
            if u.name == event_driven_user:
                user_data = u

    if user_data:
        return user_data.id
    return None


def find_in_reminder_list(
    unique_id: str, ctx_uid: str, uid: str, reminders: Sequence[ReminderItem]
):
    def reminder_filter(r: ReminderItem) -> bool:
        return r.list_id == unique_id and r.uid == uid

    found_reminder: Sequence[ReminderItem] = list(filter(reminder_filter, reminders))
    if len(found_reminder) == 0:
        LOGGER.warning(f"Item {uid} not found")
        return None
    elif len(found_reminder) > 1:
        raise ValueError(f"Multiple reminders with the same {uid} found")
    if found_reminder[0].user_id != ctx_uid:
        raise ValueError(f"{uid} belongs to a different user")
    return found_reminder[0]


def load_reminders(
    unique_id, reminders: dict[str, dict[str, str]]
) -> Sequence[ReminderItem]:
    reminders_list = []
    for r in reminders.values():
        uid = r.get("id")
        due_str = r.get("due")
        if not uid or not due_str:
            raise ValueError(
                f"Can't load reminder {r} items with no id '{uid}' or due '{due_str}'"
            )
        if not unique_id or r.get("list_id", None) != unique_id:
            continue

        last_fired = r.get("last_fired", None)
        if last_fired:
            last_fired = datetime.fromisoformat(last_fired)
        else:
            last_fired = None
        reminders_list.append(
            ReminderItem(
                uid=uid,
                list_id=unique_id,
                summary=r.get("summary"),
                due=datetime.fromisoformat(due_str),
                user_id=r.get("user_id"),
                last_fired=last_fired,
            )
        )
    return reminders_list


class UserRemindersListEntity(ReminderListEntity):
    """User Reminders To-do list entity."""

    def __init__(self, hass: HomeAssistant, user_id: str, user_name: str | None):
        self.hass = hass
        self._user_id = user_id
        self._user_name = user_name
        self._attr_name = f"{user_name}'s Reminders"
        self._attr_reminder_list = []

        from homeassistant.util import slugify

        self._attr_unique_id = f"{DOMAIN}_{slugify(user_name)}"

        self._attr_icon = "mdi:check-circle-outline"
        self._attr_supported_features = (
            ReminderListEntityFeature.CREATE_REMINDER_ITEM
            | ReminderListEntityFeature.UPDATE_REMINDER_ITEM
            | ReminderListEntityFeature.REMOVE_REMINDER_ITEM
            | ReminderListEntityFeature.GET_REMINDER_ITEM_LIST
        )
        self.entity_id = generate_entity_id(
            f"{DOMAIN}.{{}}", self._attr_unique_id, hass=hass
        )
        self._sync_reminders_to_items()

    def is_for_user(self, user_id):
        return self._user_id == user_id

    def _load_reminders(
        self, reminders: dict[str, dict[str, str]]
    ) -> Sequence[ReminderItem]:
        return load_reminders(self._attr_unique_id, reminders)

    @cached_property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def _api_item_list(item: ReminderItem) -> dict[str, str]:
        return {
            "id": item.uid,
            "summary": item.summary,
            "due": item.due.isoformat(),
        }

    def _sync_reminders_to_items(self):
        reminders = self.hass.data[DOMAIN]["reminders"]
        items = []

        for reminder in reminders.values():
            uid = reminder.get("id")
            if not uid:
                continue

            # Filter by user
            if reminder.get("user_id") != self._user_id:
                continue

            due_datetime = ReminderItemFactory.normalize_date(reminder.get("due"), uid)

            if not due_datetime:
                continue

            assert self._attr_unique_id
            item = ReminderItem(
                uid=uid,
                list_id=self._attr_unique_id,
                summary=reminder.get("summary", ""),
                due=due_datetime,
                user_id=reminder.get("user_id"),
                last_fired=reminder.get("last_fired"),
            )
            items.append(item)

        self._attr_reminder_items = items
        self._attr_reminder_list = list(
            map(UserRemindersListEntity._api_item_list, items)
        )
        LOGGER.warning(f"Loaded {len(items)} reminders for user {self._user_name}")

    def _find_in_reminder_list(self, ctx_uid, item_uid, reminders):
        assert self._attr_unique_id
        return find_in_reminder_list(self._attr_unique_id, ctx_uid, item_uid, reminders)

    async def async_create_reminder_item(
        self, call: ServiceCall, item: ReminderItemFactory
    ) -> None:
        LOGGER.debug(f"Creating reminder item: {item.summary}")

        import pdb

        pdb.set_trace()
        ctx_uid = await _get_user_from_call(
            self.hass, call
        ) or await _is_automation_driven_user(self.hass, call)
        if ctx_uid != self._user_id:
            raise Unauthorized()

        item.list_id = self._attr_unique_id

        reminder = item.build(ctx_uid)

        reminders = self.hass.data[DOMAIN]["reminders"]
        reminders[reminder.uid] = {
            "id": reminder.uid,
            "list_id": self._attr_unique_id,
            "summary": reminder.summary,
            "due": reminder.due.isoformat(),
            "user_id": ctx_uid,
            "last_fired": None,
        }

        self._sync_reminders_to_items()
        self.async_write_ha_state()
        await self.hass.data[DOMAIN]["store"].async_save(reminders)

    async def async_update_reminder_item(
        self, call: ServiceCall, item: ReminderItem
    ) -> None:
        LOGGER.debug(f"Updating reminder item: {item.uid}")
        ctx_uid = await _get_user_from_call(self.hass, call)
        if ctx_uid != self._user_id:
            raise Unauthorized()

        reminders_dict = self.hass.data[DOMAIN]["reminders"]
        reminders = self._load_reminders(reminders_dict)
        reminder = self._find_in_reminder_list(ctx_uid, item.uid, reminders)
        if not reminder:
            return

        due = ReminderItemFactory.normalize_date(item.due, item.uid)

        reminders_dict[item.uid] = {
            "id": item.uid,
            "list_id": self._attr_unique_id,
            "summary": item.summary or reminders_dict[item.uid].get("summary", ""),
            "due": due.isoformat() if due else reminders_dict[item.uid].get("due"),
            "user_id": reminders_dict[item.uid].get("user_id"),
            "last_fired": (item.last_fired.isoformat() if item.last_fired else None),
        }

        self._sync_reminders_to_items()
        self.async_write_ha_state()
        await self.hass.data[DOMAIN]["store"].async_save(reminders_dict)

    async def async_remove_reminder_items(
        self, call: ServiceCall, uids: list[str]
    ) -> None:
        LOGGER.debug(f"Deleting reminder items: {uids}")
        ctx_uid = await _get_user_from_call(self.hass, call)
        if ctx_uid != self._user_id:
            raise Unauthorized()

        reminders_dict = self.hass.data[DOMAIN]["reminders"]
        reminders = self._load_reminders(reminders_dict)
        LOGGER.debug(f"Current uids: {",".join(list(map(lambda r: r.uid, reminders)))}")
        for uid in uids:
            reminder = self._find_in_reminder_list(ctx_uid, uid, reminders)
            if reminder:
                del reminders_dict[uid]

        self._sync_reminders_to_items()
        self.async_write_ha_state()
        await self.hass.data[DOMAIN]["store"].async_save(reminders_dict)

    async def async_get_reminder_items(
        self, call: ServiceCall, uids: list[str] | None
    ) -> Sequence[ReminderItem]:
        ctx_uid = await _get_user_from_call(self.hass, call)
        LOGGER.debug(f"Getting reminder items: {uids} for {ctx_uid}")

        current_reminders = []
        reminders = self._load_reminders(self.hass.data[DOMAIN]["reminders"])
        if uids:
            for uid in uids:
                reminder = self._find_in_reminder_list(ctx_uid, uid, reminders)
                if reminder:
                    current_reminders.append(reminder)
        else:
            for r in reminders:
                if r.user_id == ctx_uid:
                    current_reminders.append(r)

        return current_reminders or []

    async def async_move_reminder_item(
        self, uid: str, previous_uid: str | None = None
    ) -> None:
        LOGGER.debug(f"Moving reminder item {uid} after {previous_uid}")
        # For now, this is a no-op as we don't maintain order in storage
        # but we need to implement it to satisfy the interface
        pass
