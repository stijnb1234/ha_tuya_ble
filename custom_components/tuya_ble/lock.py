"""The Tuya BLE integration."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Callable

from homeassistant.components.lock import (
    LockEntityDescription,
    LockEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)

TuyaBLELockGetter = (
    Callable[["TuyaBLELock", TuyaBLEProductInfo], bool | None] | None
)

TuyaBLELockIsAvailable = (
    Callable[["TuyaBLELock", TuyaBLEProductInfo], bool] | None
)

TuyaBLELockSetter = (
    Callable[["TuyaBLELock", TuyaBLEProductInfo, bool], None] | None
)

@dataclass
class TuyaBLELockMapping:
    """Tuya BLE lock mapping."""

    description: LockEntityDescription
    dp_id: int
    getter: TuyaBLELockGetter = None
    setter: TuyaBLELockSetter = None
    is_available: TuyaBLELockIsAvailable = None

@dataclass
class TuyaBLECategoryLockMapping:
    """Tuya BLE category lock mapping."""

    products: dict[str | list[str], list[TuyaBLELockMapping]] = field(default_factory=dict)

LOCK_TYPES: dict[str, TuyaBLECategoryLockMapping] = {
    "ms": TuyaBLECategoryLockMapping(
        products={
            "gumrixyt": [  # Drawer lock
                TuyaBLELockMapping(
                    dp_id=33,
                    description=LockEntityDescription(
                        key="lock",
                        name="Lock",
                        icon="mdi:lock",
                    ),
                ),
            ],
        }
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE lock."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = LOCK_TYPES.get(data.product.category)
    if not mappings:
        return

    entities: list[TuyaBLELock] = []
    product_mappings = None

    # Try product specific mappings first
    if data.product.product_id in mappings.products:
        product_mappings = mappings.products[data.product.product_id]

    if product_mappings:
        for mapping in product_mappings:
            entities.append(
                TuyaBLELock(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )

    async_add_entities(entities)


class TuyaBLELock(TuyaBLEEntity, LockEntity):
    """Tuya BLE lock."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLELockMapping,
    ) -> None:
        """Init Tuya BLE lock."""
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = super().available
        if result and self._mapping.is_available:
            result = self._mapping.is_available(self, self._product)
        return result

    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        if self._mapping.getter:
            return self._mapping.getter(self, self._product)

        datapoint = self._device.datapoints[self._mapping.dp_id]
        if datapoint:
            return bool(datapoint.value)
        return None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        if self._mapping.setter:
            self._mapping.setter(self, self._product, True)
            return

        datapoint = self._device.datapoints.get_or_create(
            self._mapping.dp_id,
            TuyaBLEDataPointType.DT_BOOL,
            False,
        )
        if datapoint:
            await datapoint.set_value(True)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        if self._mapping.setter:
            self._mapping.setter(self, self._product, False)
            return

        datapoint = self._device.datapoints.get_or_create(
            self._mapping.dp_id,
            TuyaBLEDataPointType.DT_BOOL,
            False,
        )
        if datapoint:
            await datapoint.set_value(False)
