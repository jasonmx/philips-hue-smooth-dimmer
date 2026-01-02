[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

# Philips Hue Smooth Dimming

Enables you to change a Hue bulb's brightness smoothly in automations and with non-Hue buttons, by leveraging Hue's native brightness transition features.

The result is the same premium, high-end feel that you'd get with a Philips Hue dimmer.

## Key Benefits 🔅💡🔆

* **Silky Smooth:** No more visual stuttering, overshoots and low family approval ratings when using "press to dim, release to stop" automations. Brightness transitions are predictable, continuous and visually polished, mirroring the behavior of a high-quality physical dimmer.
* **Network Friendly:** By sending only two commands to Hue (Start and Stop) instead of dozens of brightness changes, your home LAN and Hue meshes remain responsive and clear.
* **Simple Setup:** This helper extends the capabilities of your Hue lights and groups on the existing core Hue integration. No secondary login is required.

---

## Installation

**Dependency:** [Philips Hue integration](https://www.home-assistant.io/integrations/hue) connected to a V2 bridge.

### Method 1: HACS (Recommended)

1. Click the button below to open this repository in HACS:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonmx&repository=ha-hue-smooth-dimming&category=integration)

2. Click the **Download** button.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration** and search for "Philips Hue Smooth Dimming".

### Method 2: Manual
1. Copy the `hue_smooth_dimming` folder to your `/config/custom_components/` directory.
2. **Restart Home Assistant.**
3. Go to **Settings > Devices & Services > Add Integration** and search for "Philips Hue Smooth Dimming".

---

## Usage

After installation, you'll find two new services available in the automation Actions list. You can also try them out in Developer Tools -> Actions. 

### `hue_smooth_dimming.start_transition`
Initiates a smooth transition. This is typically mapped to a "Hold" or "Long Press" button trigger.

| Field | Range | Description |
| :--- | :--- | :--- |
| `target` | - | Hue light(s) or groups to control. |
| `direction` | `up` / `down` | The direction of the brightness change. |
| `sweep_time` | 1 - 3600 | Seconds to go from 0% to 100 (default 5s). |
| `limit` | 0 - 100 | Optional stop point (e.g. 1% when dimming down to keep a light turned on, as 0% is off). |

### `hue_smooth_dimming.stop_transition`
Stops an active transition. This is typically mapped to the "Release" trigger of a button.

---

## Example Usage

To achieve a "Pro" dimming experience with a button remote like the Aqara Opple or IKEA TRÅDFRI:

**Automation: Start Dimming on Hold**
```yaml
action:
  - service: hue_smooth_dimming.start_transition
    target:
      entity_id: light.living_room
    data:
      direction: "up"
      sweep_time: 5 # 5s for a full 0-100% transition
```

**Automation: Stop Dimming on Release**
```yaml
action:
  - service: hue_smooth_dimming.stop_transition
    target:
      entity_id: light.living_room
```

> [!TIP]
> **Pro Tip:** For the best performance and perfect synchronization, target **Hue Groups** rather than multiple individual bulbs. This allows the Hue Bridge to send a single Zigbee broadcast, ensuring every light in the room starts and stops at the exact same moment.
