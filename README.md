# Philips Hue Smooth Dimmer

[![HACS Default](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/) ![Version](https://img.shields.io/github/v/release/jasonmx/philips-hue-smooth-dimmer)

This integration extends the core Philips Hue integration and lets you:
* Use third-party buttons to dim your Hue lights smoothly.
* Set brightness and color temperature while lights are off.

## Key Benefits 🔅💡🔆

* **Silky Smooth:** Dimming is continuous and precise, mirroring a high-quality physical dimmer. No more jittery repeat loops.
* **Pre-Stage Lights:** Prepare your lights to turn on exactly how you want them.
* **Zero Setup:** Connects to your lights automatically via the core Philips Hue integration.

---

## Requirements:
* **Hardware:** Philips Hue Bridge V2 or Pro (V3)
* **[Philips Hue integration](https://www.home-assistant.io/integrations/hue)** installed and configured

## Installation

1. Open the Philips Hue Smooth Dimmer HACS repository

[![Open the Philips Hue Smooth Dimmer HACS repository in your Home Assistant instance.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jasonmx&repository=philips-hue-smooth-dimmer&category=integration)

2. Click **Download**
3. Restart Home Assistant
4. Add the integration

[![Add Philips Hue Smooth Dimmer to your Home Assistant instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=hue_dimmer)

---

## Usage

Use these 4 actions in the Home Assistant automation editor:

<details>
<summary><b>hue_dimmer.raise</b>: Start raising the brightness when you long-press an 'up' button. </summary>

| Field | Description |
| :--- | :--- |
| `target` | Hue lights & Hue groups |
| `sweep_time` | Duration of 0-100% sweep (default 5s) |
| `limit` | Maximum brightness limit (default 100%) |

</details>

<details>
<summary><b>hue_dimmer.lower</b>: Start lowering the brightness when you long-press a 'down' button.</summary>

| Field | Description |
| :--- | :--- |
| `target` | Hue lights and groups |
| `sweep_time` | Duration of 100-0% sweep (default 5s)  |
| `limit` | Minimum brightness limit (default 0%). Light turns off at 0%. Choose 0.2%+ to keep standard Hue lights turned on, and 2%+ for Essential series. |

</details>

<details>
<summary> <b>hue_dimmer.stop</b>: Freeze the brightness when you release a button. </summary>

| Field | Description |
| :--- | :--- |
| `target` | Hue lights and groups |

</details>

<details>
<summary><b>hue_dimmer.set_attributes</b>: Set brightness and/or color temperature without turning on.</summary>

| Field | Description |
| :--- | :--- |
| `target` | Hue lights and groups |
| `brightness` | Brightness level, 0.2–100% |
| `color_temp_kelvin` | Color temperature in Kelvin (CT lights only) |

</details>

To dim multiple lights perfectly, target a **Hue Group** instead of separate lights. This enables your Hue Bridge to sync them via a single broadcast message at the start and end of each dimming transition.

<details>
<summary>Here's a two-button dimmer example in YAML.</summary>

```yaml
actions:
  - choose:

      # Hold left button to lower brightness
      - conditions:
          - condition: trigger
            id: long_press_left
        sequence:
          - action: hue_dimmer.lower
            target:
              entity_id: light.living_room
            data:
              sweep_time: 4
              limit: 0.2

      # Hold right button to raise brightness
      - conditions:
          - condition: trigger
            id: long_press_right
        sequence:
          - action: hue_dimmer.raise
            target:
              entity_id: light.living_room
            data:
              sweep_time: 4

      # Release button to stop
      - conditions:
          - condition: trigger
            id:
              - release_left
              - release_right
        sequence:
          - action: hue_dimmer.stop
            target:
              entity_id: light.living_room
```
</details>

---

## Uninstall

This integration follows standard integration removal.

1. Open the integration

[![Open the Philips Hue Smooth Dimmer integration in your Home Assistant instance.](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=hue_dimmer)

2. Click the ⋮ menu and choose **Delete**
