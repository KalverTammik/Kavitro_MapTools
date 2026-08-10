"""Reversible edit operation for one EVEL gravity duct."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from qgis.core import (
    NULL,
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsVectorLayer,
    QgsVectorLayerUtils,
    QgsVariantUtils,
)


class GravityDuctWriteError(RuntimeError):
    """Raised when a gravity duct cannot be added safely."""


class GravityDuctWriteCanceled(GravityDuctWriteError):
    """Raised after the user cancels the configured attribute form."""


@dataclass(frozen=True)
class GravityDuctWriteResult:
    feature_id: int
    mslink: int


class GravityDuctWriter:
    """Add one gravity duct without creating sewer nodes."""

    COMMAND_TEXT = "Lisa EVEL-i isevoolne toru"

    def __init__(self, layer: QgsVectorLayer) -> None:
        self.layer = layer

    def write(
        self,
        geometry: QgsGeometry,
        open_form: Callable[[QgsVectorLayer, QgsFeature], bool],
    ) -> GravityDuctWriteResult:
        if not self.layer.isEditable():
            raise GravityDuctWriteError(
                "Isevoolse toru kiht peab olema redigeerimisrežiimis."
            )
        if (
            geometry is None
            or geometry.isNull()
            or geometry.isEmpty()
            or geometry.type() != Qgis.GeometryType.Line
            or geometry.length() <= 0
        ):
            raise GravityDuctWriteError(
                "Isevoolse toru geomeetria peab olema positiivse pikkusega joon."
            )

        length_index = self._field_index("LENGTH_2D")
        begin_node_index = self._field_index("BEGIN_NODE_ID")
        end_node_index = self._field_index("END_NODE_ID")
        self.layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            feature = QgsVectorLayerUtils.createFeature(
                self.layer,
                geometry,
                {
                    length_index: geometry.length(),
                    begin_node_index: NULL,
                    end_node_index: NULL,
                },
            )
            # Gravity ducts are initially created without sewer nodes. Clear
            # references after default evaluation too, so a legacy project
            # default cannot introduce an invalid foreign key.
            feature.setAttribute(begin_node_index, NULL)
            feature.setAttribute(end_node_index, NULL)
            if not self.layer.addFeature(feature):
                raise GravityDuctWriteError(
                    "Uue isevoolse toru lisamine andmepakkujasse ebaõnnestus."
                )

            mslink = self._required_integer_attribute(feature, "MSLINK")
            if not open_form(self.layer, feature):
                raise GravityDuctWriteCanceled(
                    "Isevoolse toru lisamine tühistati."
                )

            self.layer.endEditCommand()
            self.layer.triggerRepaint()
            return GravityDuctWriteResult(
                feature_id=int(feature.id()),
                mslink=mslink,
            )
        except Exception:
            self.layer.destroyEditCommand()
            self.layer.triggerRepaint()
            raise

    def _required_integer_attribute(
        self,
        feature: QgsFeature,
        field_name: str,
    ) -> int:
        index = self._field_index(field_name)
        value = feature.attribute(index)
        if QgsVariantUtils.isNull(value):
            raise GravityDuctWriteError(
                f"Andmepakkuja ei tagastanud uue isevoolse toru "
                f"{field_name} väärtust."
            )
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise GravityDuctWriteError(
                f"Andmepakkuja tagastatud {field_name} ei ole täisarv."
            ) from error

    def _field_index(self, field_name: str) -> int:
        index = self.layer.fields().lookupField(field_name)
        if index < 0:
            raise GravityDuctWriteError(
                f"Kihil „{self.layer.name()}“ puudub väli {field_name}."
            )
        return index
