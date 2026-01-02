import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN, DEFAULT_SWEEP_TIME

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Hue Smooth Dimming from a config entry."""
    registry = er.async_get(hass)

    async def handle_transition(call: ServiceCall):
        for entity_id in call.data.get("entity_id", []):
            if not (ent_entry := registry.async_get(entity_id)) or ent_entry.platform != "hue":
                continue
            
            bridge = hass.data["hue"].get(ent_entry.config_entry_id)
            if not bridge: continue

            if call.service == "stop_transition":
                cmd = {"dimming_delta": {"action": "stop"}}
            else:
                state = hass.states.get(entity_id)
                cur = (state.attributes.get("brightness", 0) / 255) * 100 if state else 0
                
                direction = call.data.get("direction")
                limit = call.data.get("limit")
                sweep = float(call.data.get("sweep_time", DEFAULT_SWEEP_TIME))
                
                target = float(limit) if limit is not None else (100.0 if direction == "up" else 0.0)
                dur = abs(target - cur) * sweep / 100
                cmd = {"dimming": {"brightness": target}, "dynamics": {"duration": int(dur * 1000)}, "on": True if target > 0 else None}

            await bridge.async_request_call(bridge.api.lights.set_state, id=ent_entry.unique_id, **cmd)

    hass.services.async_register(DOMAIN, "start_transition", handle_transition)
    hass.services.async_register(DOMAIN, "stop_transition", handle_transition)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload the services when the integration is removed."""
    hass.services.async_remove(DOMAIN, "start_transition")
    hass.services.async_remove(DOMAIN, "stop_transition")
    return True