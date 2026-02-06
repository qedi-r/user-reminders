"""Intent handlers for user_reminders."""

from datetime import date, datetime, timedelta
from typing import Any, Sequence
import re

from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers.intent import Intent, IntentHandler, IntentResponse
from homeassistant.helpers.intent import async_register
from homeassistant.components.conversation import default_agent
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN, LOGGER
from .reminder_entity import (
    UserRemindersListEntity,
    load_reminders,
)
from custom_components.reminders import DATA_COMPONENT
from custom_components.reminders.const import (
    ReminderItem,
    ReminderServices,
)

# 12:33, 2:33, 02:33
TWENTY_FOUR_HOUR_FORMAT_REGEX = r"^(\d{1,2}):(\d{2})$"

# 12:33am, 1:33pm, 12pm, 3am
# 12:33 will assume AM
TWELVE_HOUR_FORMAT_REGEX = r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$"

# Mapping day names to weekday numbers (Monday=0, Sunday=6)
DAY_NAME_TO_WEEKDAY = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "weds": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

TIME_UNIT_TO_TIMEDELTA = {
    "minute": timedelta(minutes=1),
    "minutes": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "hours": timedelta(hours=1),
    "day": timedelta(days=1),
    "days": timedelta(days=1),
    "week": timedelta(weeks=1),
    "weeks": timedelta(weeks=1),
}

TIME_PERIOD_TO_HOUR = {
    "morning": 9,
    "afternoon": 14,
    "evening": 18,
    "night": 21,
}

UNSET_DATE = datetime(year=1970, month=1, day=1)

TIME_FORMAT = "%A %b %-d at %-H:%M %Z"

INTENT_CREATE_REMINDER = "CreateReminder"
INTENT_COMPLETE_REMINDER = "CompleteReminder"
INTENT_LIST_REMINDERS = "ListReminders"
INTENT_UPDATE_REMINDER = "UpdateReminder"


class ReminderTimeResolver:
    @staticmethod
    def handle_relative_day(now: datetime, relative_day: str) -> datetime | None:
        relative_day = relative_day.lower()
        result_date = None
        if relative_day == "today":
            result_date = now
        elif relative_day == "tomorrow":
            result_date = now + timedelta(days=1)
        elif relative_day == "tonight":
            result_date = now
            if now.hour > 21:
                now = now + timedelta(days=1)
            result_date = now.replace(hour=21, minute=0, second=0, microsecond=0)
        elif relative_day == "next week":
            # FIX this should be the first coming monday
            result_date = now + timedelta(weeks=1)
        elif relative_day == "this week":
            # FIX this should be the the first coming friday
            result_date = now
        elif relative_day == "this weekend":
            # FIX this should be saturday, or if it is currently saturday, it will be sunday
            days_until_saturday = (5 - now.weekday()) % 7
            if days_until_saturday == 0 and now.weekday() == 5:
                result_date = now
            else:
                result_date = now + timedelta(days=days_until_saturday)
        elif relative_day == "next weekend":
            days_until_saturday = (5 - now.weekday()) % 7
            result_date = now + timedelta(days=days_until_saturday + 7)
        return result_date

    @staticmethod
    def handle_day_name(now: datetime, day_name: str) -> datetime | None:
        day_name_lower = day_name.lower()
        result_date = None
        if day_name_lower in DAY_NAME_TO_WEEKDAY:
            target_weekday = DAY_NAME_TO_WEEKDAY[day_name_lower]
            current_weekday = now.weekday()
            days_ahead = target_weekday - current_weekday
            if days_ahead <= 0:
                days_ahead += 7
            result_date = now + timedelta(days=days_ahead)
        return result_date

    @staticmethod
    def handle_relative_time(now, time_number: str, time_unit: str) -> datetime | None:
        try:
            num = int(time_number)
            unit_lower = time_unit.lower()
            if unit_lower in TIME_UNIT_TO_TIMEDELTA:
                delta = TIME_UNIT_TO_TIMEDELTA[unit_lower] * num
                return now + delta
        except ValueError:
            pass

    @staticmethod
    def handle_month_name_with_ordinal(
        now: datetime, month_name: str, ordinal: str
    ) -> datetime | None:
        month_lower = month_name.lower()
        if month_lower in MONTH_NAME_TO_NUMBER:
            month_num = MONTH_NAME_TO_NUMBER[month_lower]
            day_num = int(re.sub(r"[^\d]", "", ordinal))
            year = now.year
            if month_num < now.month or (month_num == now.month and day_num < now.day):
                year += 1
            try:
                result_date = now.replace(
                    year=year,
                    month=month_num,
                    day=day_num,
                    hour=9,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                return result_date
            except ValueError:
                pass
        return None

    @staticmethod
    def apply_time_of_day(
        result_date: datetime,
        time_period: str | None,
        hour_number: str | None,
        minute_number: str | None,
    ) -> datetime:
        if result_date.date() == UNSET_DATE.date():
            result_date = dt_util.now()
        if time_period:
            period_lower = time_period.lower()
            if period_lower in TIME_PERIOD_TO_HOUR:
                hour = TIME_PERIOD_TO_HOUR[period_lower]
                result_date = result_date.replace(
                    hour=hour, minute=0, second=0, microsecond=0
                )
        elif hour_number:
            parsed_hour, parsed_minute = ReminderTimeResolver.parse_hour_and_minute(
                hour_number, minute_number
            )
            LOGGER.debug(f"parsed hour {parsed_hour}:{parsed_minute}")
            if parsed_hour:
                result_date = result_date.replace(
                    hour=parsed_hour,
                    minute=parsed_minute or 0,
                    second=0,
                    microsecond=0,
                )
        else:
            result_date = result_date.replace(hour=9, minute=0, second=0, microsecond=0)

        if result_date < dt_util.now():
            result_date = result_date + timedelta(days=1)

        return result_date

    @staticmethod
    def is_in_relative_minutes(time_number: str | None, time_unit: str | None) -> bool:
        return (
            time_number is not None
            and time_unit is not None
            and time_unit in ["minute", "hour", "minutes", "hours"]
        )

    @staticmethod
    def parse_hour_and_minute(
        hour: str, minute: str | None
    ) -> tuple[int | None, int | None]:
        """Parse a time string like '3pm', '3:30pm', '15:00' into (hour, minute)."""
        hour = hour.lower().strip()

        if minute:
            minute = minute.lower().strip()
            # Handle 24-hour format (15:00)
            match = re.match(TWENTY_FOUR_HOUR_FORMAT_REGEX, "{hour}:{minute}")
            if match:
                return int(match.group(1)), int(match.group(2))

        time_str = hour
        if minute:
            time_str = f"{hour}:{minute}"

        # Handle 12-hour format (3pm, 3:30pm)
        match = re.match(TWELVE_HOUR_FORMAT_REGEX, time_str)
        if match:
            hour_v = int(match.group(1))
            minute_v = int(match.group(2)) if match.group(2) else None
            period = match.group(3)
            if period == "pm" and hour_v != 12:
                hour_v += 12
            elif period == "am" and hour_v == 12:
                hour_v = 0
            return hour_v, minute_v

        # Handle special times
        if hour in ("noon", "midday"):
            return 12, 0
        if hour == "midnight":
            return 0, 0

        return (None, None)


class ReminderIntentHandlerBase(IntentHandler):
    def find_entity(
        self, hass: HomeAssistant, ctx: Context
    ) -> UserRemindersListEntity | None:
        component = hass.data.get(DATA_COMPONENT)
        if not component or not component.entities:
            return None

        for entity in list(component.entities or []):
            if not entity:
                continue

            if not isinstance(entity, UserRemindersListEntity):
                continue

            if not entity.is_for_user(ctx.user_id):
                continue

            return entity

        return None

    def get_reminders(self, hass, unique_id, user_id):
        reminders_dict = hass.data[DOMAIN]["reminders"]
        reminders = load_reminders(unique_id, reminders_dict)

        def reminder_filter(r: ReminderItem) -> Sequence[ReminderItem]:
            return r.list_id == unique_id and r.user_id == user_id

        filtered_reminders: Sequence[ReminderItem] = list(
            filter(reminder_filter, reminders)
        )
        return filtered_reminders

    def matching_reminder(
        self, hass, reminder_text, unique_id, user_id
    ) -> ReminderItem | None:
        matching_reminder = None
        reminders = self.get_reminders(hass, unique_id, user_id)
        for reminder in reminders:
            if reminder_text.lower() in reminder.summary.lower():
                matching_reminder = reminder
                break
        return matching_reminder

    def get_slot_value(self, intent_obj: Intent, slot_name: str) -> str | None:
        """Extract the text value from a slot."""
        slot = intent_obj.slots.get(slot_name)
        if slot is None:
            return None
        if isinstance(slot, dict):
            return slot.get("value") or slot.get("text")
        return str(slot)

    def parse_due_from_slots(self, intent_obj: Intent) -> datetime | None:
        """Parse date/time slots into a datetime object."""
        now = dt_util.now()

        # Get all possible slots
        relative_day = self.get_slot_value(intent_obj, "relative_day")
        day_name = self.get_slot_value(intent_obj, "day_name")
        time_number = self.get_slot_value(intent_obj, "time_number")
        time_unit = self.get_slot_value(intent_obj, "time_unit")
        time_period = self.get_slot_value(intent_obj, "time_period")
        hour_number = self.get_slot_value(intent_obj, "hour_number")
        minute_number = self.get_slot_value(intent_obj, "minute_number")
        month_name = self.get_slot_value(intent_obj, "month_name")
        ordinal = self.get_slot_value(intent_obj, "ordinal")

        result_date = UNSET_DATE

        if relative_day:
            result_date = ReminderTimeResolver.handle_relative_day(now, relative_day)
        elif day_name:
            result_date = ReminderTimeResolver.handle_day_name(now, day_name)
        elif time_number and time_unit:
            result_date = ReminderTimeResolver.handle_relative_time(
                now, time_number, time_unit
            )
        elif month_name and ordinal:
            result_date = ReminderTimeResolver.handle_month_name_with_ordinal(
                now, month_name, ordinal
            )

        if result_date is None:
            result_date = now + timedelta(days=1)

        if not ReminderTimeResolver.is_in_relative_minutes(time_number, time_unit):
            result_date = ReminderTimeResolver.apply_time_of_day(
                result_date, time_period, hour_number, minute_number
            )

        return result_date


class ListRemindersIntentHandler(ReminderIntentHandlerBase):
    intent_type = INTENT_LIST_REMINDERS
    description = "List all reminders"
    slot_schema = {}  # type: ignore

    async def async_handle(self, intent_obj: Intent) -> IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        context = intent_obj.context

        entity = self.find_entity(hass, intent_obj.context)
        if not entity or not entity._attr_unique_id:
            return intent_obj.create_response()
        unique_id = entity._attr_unique_id

        reminders = self.get_reminders(hass, unique_id, context.user_id)

        if not reminders:
            response = intent_obj.create_response()
            response.async_set_speech("You have no reminders")
            return response

        reminder_list = []
        for reminder in reminders:
            reminder_list.append(
                f"{reminder.summary} (due {reminder.due.strftime(TIME_FORMAT)})"
            )

        speech = (
            f"You have {len(reminders)} reminder{'s' if len(reminders) != 1 else ''}. "
            + ", ".join(reminder_list)
        )

        response = intent_obj.create_response()
        response.async_set_speech(speech)
        return response


class CreateReminderIntentHandler(ReminderIntentHandlerBase):
    intent_type = INTENT_CREATE_REMINDER
    description = "Create a new reminder"

    slot_schema = {  # type: ignore
        vol.Required("reminder_text"): str,
        vol.Optional("time_period"): str,
        vol.Optional("hour_number"): str,
        vol.Optional("minute_number"): str,
        vol.Optional("next_day"): str,
        vol.Optional("relative_day"): str,
        vol.Optional("relative_time"): str,
        vol.Optional("specific_day"): str,
    }

    async def async_handle(self, intent_obj: Intent) -> IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        context = intent_obj.context
        reminder_text = intent_obj.slots.get("reminder_text", {}).get("text", "")

        entity = self.find_entity(hass, intent_obj.context)
        if not entity or not entity._attr_unique_id:
            return intent_obj.create_response()

        due = self.parse_due_from_slots(intent_obj)

        service_data = {
            "entity_id": entity.entity_id,
            "due": due,
            "summary": reminder_text,
        }

        await hass.services.async_call(
            "reminders",
            ReminderServices.ADD_ITEM,
            service_data,
            blocking=False,
            context=context,
        )

        response = intent_obj.create_response()
        response_text = f"I've created a reminder to {reminder_text}"
        if due:
            response_text = f"{response_text} at {due.strftime(TIME_FORMAT)}"
        response.async_set_speech(response_text)
        return response


class CompleteReminderIntentHandler(ReminderIntentHandlerBase):
    intent_type = INTENT_COMPLETE_REMINDER
    description = "Mark a reminder as complete or delete it"
    slot_schema = {  # type: ignore
        vol.Required("reminder_text"): str,
    }

    async def async_handle(self, intent_obj: Intent) -> IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        context = intent_obj.context
        reminder_text = intent_obj.slots.get("reminder_text", {}).get("text", "")

        entity = self.find_entity(hass, intent_obj.context)
        if not entity or not entity._attr_unique_id:
            return intent_obj.create_response()
        unique_id = entity._attr_unique_id

        matching_reminder = self.matching_reminder(
            hass, reminder_text, unique_id, context.user_id
        )

        if not matching_reminder:
            response = intent_obj.create_response()
            response.async_set_speech(
                f"I couldn't find a reminder matching {reminder_text}"
            )
            return response

        await hass.services.async_call(
            "reminders",
            ReminderServices.REMOVE_ITEM,
            {
                "entity_id": entity.entity_id,
                "uids": [matching_reminder.uid],
            },
            blocking=False,
            context=context,
        )

        response = intent_obj.create_response()
        response.async_set_speech(f"I've completed the reminder to {reminder_text}")
        return response


class UpdateReminderIntentHandler(ReminderIntentHandlerBase):
    intent_type = INTENT_UPDATE_REMINDER
    description = "Update an existing reminder"
    slot_schema = {  # type: ignore
        vol.Required("reminder_text"): str,
        vol.Optional("new_reminder_text"): str,
        vol.Optional("time_period"): str,
        vol.Optional("hour_number"): str,
        vol.Optional("minute_number"): str,
        vol.Optional("next_day"): str,
        vol.Optional("relative_day"): str,
        vol.Optional("relative_time"): str,
        vol.Optional("specific_day"): str,
    }

    async def async_handle(self, intent_obj: Intent) -> IntentResponse:
        """Handle the intent."""
        hass = intent_obj.hass
        context = intent_obj.context
        reminder_text = intent_obj.slots.get("reminder_text", {}).get("text", "")
        new_text = intent_obj.slots.get("new_reminder_text", {}).get("text", "")

        entity = self.find_entity(hass, intent_obj.context)
        if not entity or not entity._attr_unique_id:
            return intent_obj.create_response()
        unique_id = entity._attr_unique_id

        matching_reminder = self.matching_reminder(
            hass, reminder_text, unique_id, context.user_id
        )

        if not matching_reminder:
            response = intent_obj.create_response()
            response.async_set_speech(
                f"I couldn't find a reminder matching {reminder_text}"
            )
            return response

        updated_due = None
        if not new_text:
            updated_due = self.parse_due_from_slots(intent_obj)

        service_data = {
            "entity_id": entity.entity_id,
            "uid": matching_reminder.uid,
        }

        if new_text:
            service_data["summary"] = new_text
            service_data["due"] = matching_reminder.due.isoformat()
        elif updated_due:
            service_data["summary"] = matching_reminder.summary
            service_data["due"] = updated_due.isoformat()

        await hass.services.async_call(
            "reminders",
            ReminderServices.UPDATE_ITEM,
            service_data,
            blocking=False,
            context=context,
        )

        response = intent_obj.create_response()
        response_text = f'I\'ve updated the reminder "{reminder_text}" to "{new_text}"'
        if updated_due:
            response_text = f'I\'ve updated the reminder "{reminder_text}" be due at {updated_due.strftime(TIME_FORMAT)}'
        response.async_set_speech(response_text)
        return response


SLOT_LIST_REMINDER_TEXT = "reminder_text"


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Set up intent handlers."""
    async_register(hass, CreateReminderIntentHandler())
    async_register(hass, CompleteReminderIntentHandler())
    async_register(hass, ListRemindersIntentHandler())
    async_register(hass, UpdateReminderIntentHandler())
