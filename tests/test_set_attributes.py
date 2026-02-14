from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hue_dimmer import _handle_set_attributes
from tests.conftest import make_entity_state, make_service_call

RESOURCE_ID = "abc-123"
ENTITY_ID = "light.kitchen"


@pytest.fixture
def mock_bridge():
    bridge = MagicMock()
    bridge.api.request = AsyncMock()
    return bridge


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture(autouse=True)
def patch_extract_entity_ids():
    async def _extract(call):
        return set(call.data.get("entity_id", []))

    with patch(
        "custom_components.hue_dimmer.async_extract_entity_ids",
        side_effect=_extract,
    ):
        yield


def patch_bridge(bridge, resource_type="light"):
    return patch(
        "custom_components.hue_dimmer.get_bridge_and_id",
        new_callable=AsyncMock,
        return_value=(bridge, resource_type, RESOURCE_ID),
    )


@pytest.mark.asyncio
async def test_brightness_only(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "brightness": 42.5})

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={"dimming": {"brightness": 42.5}},
    )


@pytest.mark.asyncio
async def test_ct_only_on_ct_light(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "color_temp_kelvin": 3000})
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["color_temp"],
        min_color_temp_kelvin=2202,
        max_color_temp_kelvin=6535,
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={"color_temperature": {"mirek": 333}},
    )


@pytest.mark.asyncio
async def test_brightness_and_ct(mock_hass, mock_bridge):
    call = make_service_call({
        "entity_id": [ENTITY_ID],
        "brightness": 75,
        "color_temp_kelvin": 4000,
    })
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["color_temp"],
        min_color_temp_kelvin=2202,
        max_color_temp_kelvin=6535,
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={
            "dimming": {"brightness": 75.0},
            "color_temperature": {"mirek": 250},
        },
    )


@pytest.mark.asyncio
async def test_ct_on_non_ct_light_with_brightness(mock_hass, mock_bridge):
    call = make_service_call({
        "entity_id": [ENTITY_ID],
        "brightness": 50,
        "color_temp_kelvin": 3000,
    })
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["brightness"],
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    # CT skipped, brightness still sent
    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={"dimming": {"brightness": 50.0}},
    )


@pytest.mark.asyncio
async def test_ct_only_on_non_ct_light(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "color_temp_kelvin": 3000})
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["brightness"],
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    # No payload to send — API should not be called
    mock_bridge.api.request.assert_not_called()


@pytest.mark.asyncio
async def test_no_fields_provided(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID]})

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_not_called()


@pytest.mark.asyncio
async def test_ct_clamped_to_min(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "color_temp_kelvin": 1000})
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["color_temp"],
        min_color_temp_kelvin=2202,
        max_color_temp_kelvin=6535,
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    # 1000K clamped to min 2202K → mirek = round(1_000_000 / 2202) = 454
    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={"color_temperature": {"mirek": 454}},
    )


@pytest.mark.asyncio
async def test_ct_clamped_to_max(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "color_temp_kelvin": 9000})
    mock_hass.states.get.return_value = make_entity_state(
        supported_color_modes=["color_temp"],
        min_color_temp_kelvin=2202,
        max_color_temp_kelvin=6535,
    )

    with patch_bridge(mock_bridge):
        await _handle_set_attributes(mock_hass, call)

    # 9000K clamped to max 6535K → mirek = round(1_000_000 / 6535) = 153
    mock_bridge.api.request.assert_called_once_with(
        "put",
        f"clip/v2/resource/light/{RESOURCE_ID}",
        json={"color_temperature": {"mirek": 153}},
    )


@pytest.mark.asyncio
async def test_api_error_handled(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "brightness": 50})
    mock_bridge.api.request.side_effect = Exception("Connection refused")

    with patch_bridge(mock_bridge):
        # Should not raise
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_called_once()


def _setup_group_bridge(mock_bridge, light_ids, owner_rtype="zone"):
    # Wire up: grouped_light → owner → REST API returns children with light references
    grouped_light = MagicMock()
    grouped_light.owner.rid = "zone-1"
    grouped_light.owner.rtype.value = owner_rtype

    # Mock REST API: GET zone returns children as light references (aiohue returns list directly)
    zone_resp = [{"children": [{"rtype": "light", "rid": lid} for lid in light_ids]}]

    async def mock_request(method, path, **kwargs):
        if method == "get" and f"/{owner_rtype}/zone-1" in path:
            return zone_resp
        return None

    mock_bridge.api.groups.grouped_light.get.return_value = grouped_light
    mock_bridge.api.request = AsyncMock(side_effect=mock_request)


@pytest.mark.asyncio
async def test_group_resolves_to_individual_lights(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "brightness": 80})
    _setup_group_bridge(mock_bridge, ["light-1", "light-2"])

    with patch_bridge(mock_bridge, resource_type="grouped_light"):
        await _handle_set_attributes(mock_hass, call)

    # 1 GET for zone + 2 PUTs for individual lights = 3 calls
    assert mock_bridge.api.request.call_count == 3
    expected_payload = {"dimming": {"brightness": 80.0}}
    put_calls = [c for c in mock_bridge.api.request.call_args_list if c.args[0] == "put"]
    assert len(put_calls) == 2
    called_paths = {c.args[1] for c in put_calls}
    assert called_paths == {
        "clip/v2/resource/light/light-1",
        "clip/v2/resource/light/light-2",
    }
    for c in put_calls:
        assert c.kwargs["json"] == expected_payload


@pytest.mark.asyncio
async def test_group_no_lights_found(mock_hass, mock_bridge):
    call = make_service_call({"entity_id": [ENTITY_ID], "brightness": 50})
    mock_bridge.api.groups.grouped_light.get.return_value = None
    mock_bridge.api.request = AsyncMock()

    with patch_bridge(mock_bridge, resource_type="grouped_light"):
        await _handle_set_attributes(mock_hass, call)

    mock_bridge.api.request.assert_not_called()
