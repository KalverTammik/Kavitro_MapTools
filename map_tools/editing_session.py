"""Ownership-aware QGIS editing sessions used by EVEL map tools."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import QgsProject, QgsVectorLayer


@dataclass(frozen=True)
class EditingSessionResult:
    committed: bool
    left_in_existing_session: bool = False
    errors: tuple[str, ...] = ()


class PluginEditingSession:
    """Commit or roll back only sessions which the plugin itself opened."""

    def __init__(self, layers) -> None:
        unique = []
        seen = set()
        for layer in layers:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            unique.append(layer)
        self.layers: tuple[QgsVectorLayer, ...] = tuple(unique)
        self.initially_editable = {
            layer.id(): layer.isEditable() for layer in self.layers
        }

    @property
    def owns_session(self) -> bool:
        return bool(self.layers) and not any(self.initially_editable.values())

    def commit(self) -> EditingSessionResult:
        if not self.owns_session:
            return EditingSessionResult(
                committed=False,
                left_in_existing_session=True,
            )
        project = QgsProject.instance()
        errors = []
        for layer in self.layers:
            if not layer.isEditable():
                continue
            if project.mapLayer(layer.id()) is layer:
                success, layer_errors = project.commitChanges(
                    True,
                    layer,
                )
            else:
                success = layer.commitChanges(True)
                layer_errors = layer.commitErrors()
            if not success:
                errors.extend(str(error) for error in layer_errors)
                return EditingSessionResult(
                    committed=False,
                    errors=tuple(errors),
                )
        return EditingSessionResult(committed=True)

    def rollback(self) -> tuple[str, ...]:
        if not self.owns_session:
            return ()
        project = QgsProject.instance()
        errors = []
        for layer in self.layers:
            if not layer.isEditable():
                continue
            if project.mapLayer(layer.id()) is layer:
                success, layer_errors = project.rollBack(True, layer)
            else:
                success = layer.rollBack(True)
                layer_errors = layer.commitErrors()
            if not success:
                errors.extend(str(error) for error in layer_errors)
        return tuple(errors)
