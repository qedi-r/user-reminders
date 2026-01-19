import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, CONF_IGNORED_USERS


class UserRemindersConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for User Reminders integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="User Reminders",
                data={CONF_IGNORED_USERS: user_input.get(CONF_IGNORED_USERS, [])},
            )

        # Get all users from Home Assistant
        users = await self.hass.auth.async_get_users()
        user_options = {}
        for user in users:
            if not user.system_generated and user.name:
                user_options[user.id] = user.name

        schema = vol.Schema(
            {
                vol.Optional(CONF_IGNORED_USERS, default=[]): cv.multi_select(
                    user_options
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)
