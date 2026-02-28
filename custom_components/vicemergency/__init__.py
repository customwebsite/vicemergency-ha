"""VicEmergency integration for Home Assistant.

Monitors incidents and warnings from the VicEmergency GeoJSON feed
with support for multiple monitoring zones.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EXCLUDE_CATEGORIES,
    CONF_INCLUDE_STATEWIDE,
    CONF_NAME,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_RADIUS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import VicEmergencyCoordinator, ZoneConfig

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.GEO_LOCATION,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the VicEmergency integration (once, not per entry)."""
    hass.data.setdefault(DOMAIN, {"coordinator": None, "entries": {}})

    card_dir = Path(__file__).parent / "www"
    if card_dir.is_dir():
        url_path = f"/{DOMAIN}_ui"
        hass.http.register_static_path(url_path, str(card_dir), cache_headers=True)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a VicEmergency zone from a config entry."""
    data = hass.data[DOMAIN]

    zone_config = ZoneConfig(
        entry_id=entry.entry_id,
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        latitude=entry.data["latitude"],
        longitude=entry.data["longitude"],
        radius_km=entry.data.get(CONF_RADIUS, DEFAULT_RADIUS),
        exclude_categories=entry.options.get(CONF_EXCLUDE_CATEGORIES, []),
        include_statewide=entry.options.get(CONF_INCLUDE_STATEWIDE, True),
        scan_interval=int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )

    coordinator: VicEmergencyCoordinator | None = data["coordinator"]
    if coordinator is None:
        coordinator = VicEmergencyCoordinator(hass, zone_config.scan_interval)
        data["coordinator"] = coordinator

    coordinator.add_zone(zone_config)

    data["entries"][entry.entry_id] = {
        "coordinator": coordinator,
        "zone_config": zone_config,
    }

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a VicEmergency zone."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = hass.data[DOMAIN]
    coordinator: VicEmergencyCoordinator | None = data["coordinator"]

    if coordinator is not None:
        coordinator.remove_zone(entry.entry_id)
        if coordinator.is_empty:
            data["coordinator"] = None

    data["entries"].pop(entry.entry_id, None)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
