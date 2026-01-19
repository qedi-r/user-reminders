from datetime import datetime, timedelta, timezone

from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from custom_components.reminders.const import ReminderItem, ReminderServices


from .const import DOMAIN, EVENT_REMINDER_DUE, LOGGER

CHECK_INTERVAL = timedelta(seconds=10)


def last_fired_in_over_24h(r: ReminderItem):
    if r.last_fired is None:
        return True
    twenty_four_hours_ago = datetime.now().astimezone(tz=timezone.utc) - timedelta(
        hours=24
    )
    if r.last_fired <= twenty_four_hours_ago:
        return True
    return False


class Scheduler:
    time_interval_cancel: CALLBACK_TYPE | None = None

    def start_scheduler(self, hass: HomeAssistant):
        async def _check(now):
            LOGGER.debug("running scheduler")
            reminders = []
            for r in hass.data[DOMAIN]["reminders"].values():
                uid = r.get("id")
                last_fired = r.get("last_fired")
                if last_fired:
                    last_fired = datetime.fromisoformat(last_fired)
                r = ReminderItem(
                    uid=uid,
                    list_id=r.get("list_id"),
                    summary=r.get("summary"),
                    due=datetime.fromisoformat(r.get("due")),
                    user_id=r.get("user_id"),
                    last_fired=last_fired,
                )

                if r.due <= now and last_fired_in_over_24h(r):
                    LOGGER.error(f"firing todo for {r.summary}")
                    hass.bus.async_fire(
                        EVENT_REMINDER_DUE,
                        {
                            "uid": r.uid,
                            "summary": r.summary,
                            "due": r.due.isoformat(),
                            "user_id": r.user_id,
                            "list_id": r.list_id,
                        },
                    )
                    service_data = {
                        "entity_id": "reminders." + r.list_id,
                        "uid": uid,
                        "summary": r.summary,
                        "due": r.due.isoformat(),
                        "last_fired": now,
                    }
                    await hass.services.async_call(
                        "reminders",
                        ReminderServices.UPDATE_ITEM,
                        service_data,
                        blocking=False,
                        context=Context(user_id=r.user_id),
                    )

        self.time_interval_cancel = async_track_time_interval(
            hass, _check, CHECK_INTERVAL
        )

    async def stop_scheduler(self):
        LOGGER.debug("stopping scheduler")
        if self.time_interval_cancel:
            self.time_interval_cancel()
