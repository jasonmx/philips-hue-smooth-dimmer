import time
import asyncio
import logging
from homeassistant.core import ServiceCall, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, DEFAULT_SWEEP_TIME, STALE_BRIGHTNESS_GUARD_SECONDS

_LOGGER = logging.getLogger(__name__)

# Tracker: { resource_id: { "time": float, "bright": float, "target": float, "dir": str, "sweep": float } }
STATE_TRACKER = {}

async def get_bridge_and_id(hass: HomeAssistant, entity_id: str):
    """Retrieves the Hue Bridge instance and Resource UUID."""
    from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
    
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if not entry or entry.platform != HUE_DOMAIN:
        _LOGGER.error("Entity %s is not a Philips Hue entity.", entity_id)
        return None, None

    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    bridge = getattr(config_entry, "runtime_data", None)
    if not bridge:
        _LOGGER.error("Hue bridge runtime_data not found for %s", entity_id)
        return None, None

    resource_id = entry.unique_id
    if "-" in resource_id and ":" in resource_id:
        resource_id = resource_id.split(":")[-1]
    
    return bridge, resource_id

# During transitions, Hue's reported brightness snaps to the target value (e.g. 100% when raising).
# If you stop a transition mid-flight (e.g. by releasing a dimmer button), the entity's actual brightness
# will differ from the reported brightness for several seconds until the API catches up. The resolver's
# job is to determine when Hue's reported brightness is likely to differ from actual, and to predict the
# actual brightness in such cases. This ensures dimming continues to operate smoothly during rapid 
# "start dimming, stop dimming, start dimming again" sequences.
def resolve_current_brightness(resource_id, api_brightness):
    """Hybrid prediction logic that detects snaps to the last known target."""
    state = STATE_TRACKER.get(resource_id)
    if not state:
        return api_brightness

    now = time.time()
    elapsed = now - state["time"]

    is_target_snap = abs(api_brightness - state["target"]) < 0.2

    if state["dir"] == "none":
        if is_target_snap and elapsed < STALE_BRIGHTNESS_GUARD_SECONDS:
            _LOGGER.info("SNAP DETECTED [%s]: API snapped to prior target %.1f%%. Using stored %.1f%%.", 
                         resource_id, api_brightness, state["bright"])
            return state["bright"]
            
        if not is_target_snap and abs(api_brightness - state["bright"]) > 5.0:
            _LOGGER.info("EXTERNAL CHANGE [%s]: API reported %.1f%% (Stored: %.1f%%). Clearing tracker.", 
                         resource_id, api_brightness, state["bright"])
            STATE_TRACKER.pop(resource_id, None)
            return api_brightness
        
        return state["bright"] if elapsed < STALE_BRIGHTNESS_GUARD_SECONDS else api_brightness

    is_within_window = elapsed < (state["sweep"] * 1.05)

    if is_target_snap and is_within_window:
        change = (100.0 / state["sweep"]) * elapsed
        if state["dir"] == "up":
            predicted = min(state["bright"] + change, 100.0)
        else:
            predicted = max(state["bright"] - change, 0.0)
        
        _LOGGER.info("SNAP DETECTED [%s]: Moving snap to %.1f%%. Predicted: %.1f%%.", 
                     resource_id, api_brightness, predicted)
        return predicted

    if elapsed > STALE_BRIGHTNESS_GUARD_SECONDS:
        STATE_TRACKER.pop(resource_id, None)

    return api_brightness

async def start_transition(bridge, resource_id, direction, sweep, limit, turn_off_at_zero=False):
    """Executes transition and stores state metadata for snap protection."""
    try:
        response = await bridge.api.request("get", f"clip/v2/resource/light/{resource_id}")
        real_data = response[0] if isinstance(response, list) else response
        api_bright = float(real_data.get("dimming", {}).get("brightness", 0.0))
    except Exception as e:
        _LOGGER.error("Failed to fetch state for %s: %s", resource_id, e)
        return

    current_bright = resolve_current_brightness(resource_id, api_bright)
    distance = abs(limit - current_bright)
    dur_ms = int(distance * sweep * 10)
    
    _LOGGER.info("CALC [%s]: %.1f%% -> %.1f%% (Dist: %.1f%%) | Duration: %dms | Turn Off @ 0: %s", 
                 resource_id, current_bright, limit, distance, dur_ms, turn_off_at_zero)

    # Allow transition if distance > 0.2 OR if we need to send the 'off' command at 0%
    should_turn_off = turn_off_at_zero and limit == 0
    if distance <= 0.2 and not should_turn_off:
        return

    STATE_TRACKER[resource_id] = {
        "time": time.time(),
        "bright": current_bright,
        "target": limit,
        "dir": direction,
        "sweep": sweep
    }
    
    payload = {
        "dimming": {"brightness": limit},
        "dynamics": {"duration": dur_ms}
    }

    if direction == "up":
        payload["on"] = {"on": True}
    elif direction == "down" and should_turn_off:
        payload["on"] = {"on": False}

    await bridge.api.request("put", f"clip/v2/resource/light/{resource_id}", json=payload)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Register services for the Hue Smooth Dimmer."""

    async def handle_raise(call: ServiceCall):
        for entity_id in call.data.get("entity_id", []):
            bridge, resource_id = await get_bridge_and_id(hass, entity_id)
            if bridge and resource_id:
                sweep = float(call.data.get("sweep_time", DEFAULT_SWEEP_TIME))
                limit = float(call.data.get("limit", 100.0))
                await start_transition(bridge, resource_id, "up", sweep, limit)

    async def handle_lower(call: ServiceCall):
        # Default to False
        turn_off_at_zero = bool(call.data.get("turn_off_at_zero", False))
        
        for entity_id in call.data.get("entity_id", []):
            bridge, resource_id = await get_bridge_and_id(hass, entity_id)
            if bridge and resource_id:
                sweep = float(call.data.get("sweep_time", DEFAULT_SWEEP_TIME))
                limit = float(call.data.get("limit", 0.0))
                await start_transition(bridge, resource_id, "down", sweep, limit, turn_off_at_zero=turn_off_at_zero)

    async def handle_stop(call: ServiceCall):
        for entity_id in call.data.get("entity_id", []):
            bridge, resource_id = await get_bridge_and_id(hass, entity_id)
            if not bridge or not resource_id: continue
            
            await bridge.api.request("put", f"clip/v2/resource/light/{resource_id}", 
                                      json={"dimming_delta": {"action": "stop"}})
            
            try:
                response = await bridge.api.request("get", f"clip/v2/resource/light/{resource_id}")
                api_bright = float(response[0].get("dimming", {}).get("brightness", 0.0))
            except:
                api_bright = 0.0
                
            final_bright = resolve_current_brightness(resource_id, api_bright)
            old_state = STATE_TRACKER.get(resource_id, {})
            
            STATE_TRACKER[resource_id] = {
                "time": time.time(),
                "bright": final_bright,
                "target": old_state.get("target", final_bright),
                "dir": "none",
                "sweep": 1.0
            }
            _LOGGER.info("STOP [%s]: Halted at predicted %.1f%%", resource_id, final_bright)

    hass.services.async_register(DOMAIN, "raise", handle_raise)
    hass.services.async_register(DOMAIN, "lower", handle_lower)
    hass.services.async_register(DOMAIN, "stop", handle_stop)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for svc in ["raise", "lower", "stop"]:
        hass.services.async_remove(DOMAIN, svc)
    return True