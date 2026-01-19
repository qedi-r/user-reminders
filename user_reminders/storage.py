from homeassistant.helpers.storage import Store
from .const import STORE_VERSION, STORE_KEY


class ReminderStore(Store):
    def __init__(self, hass):
        super().__init__(hass, STORE_VERSION, STORE_KEY)
