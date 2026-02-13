import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from .const import (
    API_SETTLE_SECONDS,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_SWEEP_TIME,
    DOMAIN,
    SERVICE_LOWER,
    SERVICE_RAISE,
    SERVICE_STOP,
)

_LOGGER = logging.getLogger(__name__)

# { (resource_type, resource_id):
#   { "time": float, "bright": float, "target": float, "dir": str, "sweep": float } }
BRIGHTNESS_CACHE = {}


async def get_bridge_and_id(hass: HomeAssistant, entity_id: str):
    # Retrieves the Hue Bridge instance and Resource UUID, ensuring it supports V2 API.
    from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN

    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)

    if not entry:
        _LOGGER.error("Entity %s not found in entity registry.", entity_id)
        return None, None, None

    config_entry = hass.config_entries.async_get_entry(entry.config_entry_id)
    if not config_entry or config_entry.domain != HUE_DOMAIN:
        _LOGGER.error("Entity %s is not a Philips Hue entity.", entity_id)
        return None, None, None

    bridge = getattr(config_entry, "runtime_data", None)

    if not bridge:
        _LOGGER.error("Hue bridge runtime_data not found for %s", entity_id)
        return None, None, None

    # V2 Bridge Check
    if getattr(bridge, "api_version", 1) < 2:
        _LOGGER.error("Hue Smooth Dimmer requires a Bridge V2 or Bridge Pro for %s", entity_id)
        return None, None, None

    resource_id = entry.unique_id

    if ":" in resource_id:
        resource_id = resource_id.split(":")[-1]

    state = hass.states.get(entity_id)
    is_group = bool(state and state.attributes.get("is_hue_group"))
    resource_type = "grouped_light" if is_group else "light"

    return bridge, resource_type, resource_id


def _get_ha_brightness(hass: HomeAssistant, entity_id: str):
    # Read brightness from HA entity state (0-255) and convert to Hue percentage (0-100).
    state = hass.states.get(entity_id)
    if not state:
        return 0.0
    ha_bright = state.attributes.get("brightness")
    return (ha_bright / 255 * 100) if ha_bright is not None else 0.0


def resolve_current_brightness(tracker_key, reported_brightness):
    # During a dimming transition, the Hue API (and therefore HA's entity state) reports
    # brightness as though the transition happened instantaneously. If a transition stops
    # mid-flight, it takes ~10s to correct its reporting.
    #
    # The resolver decides whether to trust the reported brightness or predict its own, to
    # ensure dim-stop-dim sequences work smoothly. Expired cache entries are pruned inline.

    cached = BRIGHTNESS_CACHE.get(tracker_key)
    if not cached:
        return reported_brightness

    now = time.time()
    elapsed = now - cached["time"]

    # Dynamic guard window: sweep duration + API settle buffer for active transitions,
    # just the settle buffer for stopped entries.
    guard_seconds = cached["sweep"] + API_SETTLE_SECONDS if cached["dir"] != "none" else API_SETTLE_SECONDS

    # Guard expired — trust the reported brightness and prune the cache entry
    if elapsed > guard_seconds:
        BRIGHTNESS_CACHE.pop(tracker_key, None)
        return reported_brightness

    # Guard active — predict brightness instead of trusting the report.

    # Stopped: return the cached brightness from when we stopped
    if cached["dir"] == "none":
        _LOGGER.debug(
            "CACHE [%s]: Guard active (Stationary). Ignoring reported %.1f%%. Staying at %.1f%%",
            tracker_key,
            reported_brightness,
            cached["bright"],
        )
        return cached["bright"]

    # Moving: extrapolate brightness based on elapsed time
    safe_sweep = max(cached["sweep"], 0.1)
    change = (100.0 / safe_sweep) * elapsed

    if cached["dir"] == "up":
        predicted = min(cached["bright"] + change, cached["target"])
    else:
        predicted = max(cached["bright"] - change, cached["target"])

    _LOGGER.debug(
        "CACHE [%s]: Guard active (Moving). Reported: %.1f%%, Predicted: %.1f%%",
        tracker_key,
        reported_brightness,
        predicted,
    )

    return predicted


async def start_transition(hass, bridge, resource_type, resource_id, entity_id, direction, sweep, limit):
    tracker_key = (resource_type, resource_id)
    reported_bright = _get_ha_brightness(hass, entity_id)
    current_bright = resolve_current_brightness(tracker_key, reported_bright)
    distance = abs(limit - current_bright)
    dur_ms = int(distance * sweep * 10)  # 1000ms / 100% = 10ms/%

    _LOGGER.info("CALC [%s]: %.1f%% -> %.1f%% | Dur: %dms", resource_id, current_bright, limit, dur_ms)

    if distance < 0.2:  # Min brightness step is 0.2%
        return

    BRIGHTNESS_CACHE[tracker_key] = {
        "time": time.time(),
        "bright": current_bright,
        "target": limit,
        "dir": direction,
        "sweep": sweep,
    }

    payload = {"dimming": {"brightness": limit}, "dynamics": {"duration": dur_ms}}
    if direction == "up":
        payload["on"] = {"on": True}
    elif direction == "down" and limit == 0.0:
        payload["on"] = {"on": False}  # Turn off light after fading to 0% brightness

    try:
        await bridge.api.request("put", f"clip/v2/resource/{resource_type}/{resource_id}", json=payload)
    except Exception as exc:
        _LOGGER.debug("Transition command ignored for %s: %s", resource_id, exc)


async def _handle_transition(hass: HomeAssistant, call: ServiceCall, direction: str, default_limit: float):
    sweep = float(call.data.get("sweep_time", DEFAULT_SWEEP_TIME))
    sweep = max(sweep, 0.1)  # Restricts user-supplied value to +ve numbers
    limit = float(call.data.get("limit", default_limit))

    for entity_id in call.data.get("entity_id", []):
        bridge, resource_type, resource_id = await get_bridge_and_id(hass, entity_id)
        if bridge and resource_id:
            await start_transition(hass, bridge, resource_type, resource_id, entity_id, direction, sweep, limit)


async def _handle_stop(hass: HomeAssistant, call: ServiceCall):
    for entity_id in call.data.get("entity_id", []):
        bridge, resource_type, resource_id = await get_bridge_and_id(hass, entity_id)
        if not bridge or not resource_id:
            continue

        try:
            await bridge.api.request(
                "put", f"clip/v2/resource/{resource_type}/{resource_id}", json={"dimming_delta": {"action": "stop"}}
            )
        except Exception as exc:
            _LOGGER.debug("Stop command ignored for %s: %s", resource_id, exc)

        tracker_key = (resource_type, resource_id)
        reported_bright = _get_ha_brightness(hass, entity_id)
        final_bright = resolve_current_brightness(tracker_key, reported_bright)
        old_state = BRIGHTNESS_CACHE.get(tracker_key, {})
        BRIGHTNESS_CACHE[tracker_key] = {
            "time": time.time(),
            "bright": final_bright,
            "target": old_state.get("target", final_bright),
            "dir": "none",
            "sweep": 1.0,
        }

        _LOGGER.info(
            "STOP [%s]: Halted at %.1f%% (Guarding against snap to %.1f%%)",
            resource_id,
            final_bright,
            BRIGHTNESS_CACHE[tracker_key]["target"],
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    # Register services for the Hue Smooth Dimmer.

    async def handle_raise(call: ServiceCall):
        await _handle_transition(hass, call, "up", DEFAULT_MAX_BRIGHTNESS)

    async def handle_lower(call: ServiceCall):
        await _handle_transition(hass, call, "down", DEFAULT_MIN_BRIGHTNESS)

    async def handle_stop(call: ServiceCall):
        await _handle_stop(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_RAISE, handle_raise)
    hass.services.async_register(DOMAIN, SERVICE_LOWER, handle_lower)
    hass.services.async_register(DOMAIN, SERVICE_STOP, handle_stop)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    for svc in [SERVICE_RAISE, SERVICE_LOWER, SERVICE_STOP]:
        hass.services.async_remove(DOMAIN, svc)
    return True
