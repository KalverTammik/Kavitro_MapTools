"""QGIS plugin lifecycle and the persistent EVEL toolbar."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QMenu,
    QStyle,
    QToolButton,
)
from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsVectorLayer

from .layers import (
    DuctLayerCatalog,
    DuctLayerOption,
    DuctWorkflow,
    EVELProjectInspector,
    ConnectionPointInspector,
    HydrantInspector,
    ProjectInspection,
    SewerManholeInspector,
    SewerPumpingStationInspector,
)
from .map_tools import (
    AddGravityDuctController,
    AddWaterDuctController,
    ConnectionPointConfiguratorController,
    EditDuctController,
    FlowDirectionController,
    HydrantConfiguratorController,
    NodeConfiguratorController,
    SewerManholeConfiguratorController,
    SewerPumpingStationConfiguratorController,
)
from .importer import EvelImportTargetInspector
from .ui import (
    DiagnosticsDialog,
    EvelClearDataDialog,
    EvelImportDialog,
    CoordinateDuctDialog,
    CoordinateDuctInputError,
    VisualNodeConfiguratorDialog,
)
from .ui.light_style import apply_evel_toolbar_light_style
from .ui.icon_catalog import (
    ICON_ADD_DUCT,
    ICON_CHECK_NETWORK,
    ICON_CLEAR_DATA,
    ICON_CONFIGURE_NODE,
    ICON_CONNECTION_POINT,
    ICON_COORDINATE_DUCT,
    ICON_EDIT_DUCT,
    ICON_ERROR,
    ICON_HYDRANT,
    ICON_IMPORT,
    ICON_PUMPING_STATION,
    ICON_REFRESH,
    ICON_REPAIR_NETWORK,
    ICON_REVERSE_FLOW,
    ICON_SEWER_MANHOLE,
    ICON_STATUS_OK,
    ICON_STATUS_WARNING,
    catalog_icon,
    set_catalog_icon,
)


MESSAGE_TAG = "EVEL Võrgutööriistad"
TOOLBAR_OBJECT_NAME = "EVELNetworkToolsToolbar"


class EVELNetworkToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.toolbar = None
        self.status_action = None
        self.status_menu = None
        self.add_duct_action = None
        self.add_duct_menu = None
        self.edit_duct_action = None
        self.configure_node_action = None
        self.hydrant_action = None
        self.connection_point_action = None
        self.sewer_manhole_action = None
        self.sewer_pumping_station_action = None
        self.import_action = None
        self.clear_data_action = None
        self.reverse_action = None
        self.check_action = None
        self.repair_action = None
        self._connections = []
        self._inspection: ProjectInspection | None = None
        self._inspector = EVELProjectInspector()
        self._duct_catalog = DuctLayerCatalog(self._inspector)
        self._duct_options: tuple[DuctLayerOption, ...] = ()
        self._selected_duct_layer_id = ""
        self._sewer_manhole_inspector = SewerManholeInspector()
        self._hydrant_inspector = HydrantInspector()
        self._hydrant_ready = False
        self._connection_point_inspector = ConnectionPointInspector()
        self._connection_point_ready = False
        self._sewer_manhole_ready = False
        self._sewer_pumping_station_inspector = (
            SewerPumpingStationInspector()
        )
        self._sewer_pumping_station_ready = False
        self._import_target_inspector = EvelImportTargetInspector()
        self._import_ready = False
        self._import_reason = ""
        self._import_dialog: EvelImportDialog | None = None
        self._clear_data_dialog: EvelClearDataDialog | None = None
        self._diagnostics_dialog: DiagnosticsDialog | None = None
        self._add_controller: AddWaterDuctController | None = None
        self._gravity_controller: AddGravityDuctController | None = None
        self._edit_duct_controller: EditDuctController | None = None
        self._flow_direction_controller: FlowDirectionController | None = None
        self._node_configurator: NodeConfiguratorController | None = None
        self._hydrant_configurator: HydrantConfiguratorController | None = None
        self._connection_point_configurator: (
            ConnectionPointConfiguratorController | None
        ) = None
        self._sewer_manhole_configurator: (
            SewerManholeConfiguratorController | None
        ) = None
        self._sewer_pumping_station_configurator: (
            SewerPumpingStationConfiguratorController | None
        ) = None

    def initGui(self):  # noqa: N802 - QGIS plugin API name
        self.toolbar = self.iface.addToolBar("EVEL Võrgutööriistad")
        self.toolbar.setObjectName(TOOLBAR_OBJECT_NAME)

        self.status_action = QAction("EVEL · olek", self.iface.mainWindow())
        self.status_action.setObjectName("EVELNetworkStatusAction")
        self.status_action.triggered.connect(self.show_diagnostics)
        self.status_menu = QMenu(self.iface.mainWindow())
        self.status_menu.setObjectName("EVELStatusMenu")
        self.status_menu.setToolTipsVisible(True)
        self.status_action.setMenu(self.status_menu)
        self.toolbar.addAction(self.status_action)
        apply_evel_toolbar_light_style(self.toolbar, self.status_menu)
        status_button = self.toolbar.widgetForAction(self.status_action)
        if isinstance(status_button, QToolButton):
            status_button.setObjectName("EVELStatusToolButton")
            status_button.setPopupMode(QToolButton.InstantPopup)
            status_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._connect(self.status_menu.aboutToShow, self._rebuild_status_menu)
        self.toolbar.addSeparator()

        self.add_duct_action = self._add_tool_action(
            "Lisa toru",
            "EVELAddDuctAction",
            ICON_ADD_DUCT,
        )
        self.add_duct_action.setCheckable(True)
        self.add_duct_menu = QMenu(self.iface.mainWindow())
        self.add_duct_menu.setObjectName("EVELAddDuctMenu")
        apply_evel_toolbar_light_style(
            self.toolbar,
            self.add_duct_menu,
        )
        self.add_duct_action.setMenu(self.add_duct_menu)
        add_button = self.toolbar.widgetForAction(self.add_duct_action)
        if isinstance(add_button, QToolButton):
            add_button.setPopupMode(QToolButton.InstantPopup)
        self._add_controller = AddWaterDuctController(
            self.iface,
            self.add_duct_action,
            self.refresh_state,
        )
        self._gravity_controller = AddGravityDuctController(
            self.iface,
            self.add_duct_action,
            self.refresh_state,
        )
        self.edit_duct_action = self._add_tool_action(
            "Vaata/muuda toru",
            "EVELEditDuctAction",
            ICON_EDIT_DUCT,
        )
        self.edit_duct_action.setCheckable(True)
        self.edit_duct_action.triggered.connect(self._toggle_edit_duct)
        self._edit_duct_controller = EditDuctController(
            self.iface,
            self.edit_duct_action,
            self.refresh_state,
        )
        self.configure_node_action = self._add_tool_action(
            "Konfigureeri sõlm",
            "EVELConfigureWaterNodeAction",
            ICON_CONFIGURE_NODE,
        )
        self.configure_node_action.setCheckable(True)
        self.configure_node_action.triggered.connect(
            self._toggle_configure_node
        )
        self._node_configurator = NodeConfiguratorController(
            self.iface,
            self.configure_node_action,
            self.refresh_state,
            dialog_class=VisualNodeConfiguratorDialog,
        )
        self.hydrant_action = self._add_tool_action(
            "Hüdrant",
            "EVELHydrantAction",
            ICON_HYDRANT,
        )
        self.hydrant_action.setCheckable(True)
        self.hydrant_action.triggered.connect(self._toggle_hydrant)
        self._hydrant_configurator = HydrantConfiguratorController(
            self.iface,
            self.hydrant_action,
            self.refresh_state,
        )
        self.connection_point_action = self._add_tool_action(
            "Liitumispunkt",
            "EVELConnectionPointAction",
            ICON_CONNECTION_POINT,
        )
        self.connection_point_action.setCheckable(True)
        self.connection_point_action.triggered.connect(
            self._toggle_connection_point
        )
        self._connection_point_configurator = (
            ConnectionPointConfiguratorController(
                self.iface,
                self.connection_point_action,
                self.refresh_state,
            )
        )
        self.sewer_manhole_action = self._add_tool_action(
            "Kaev / põlv",
            "EVELSewerManholeClockAction",
            ICON_SEWER_MANHOLE,
        )
        self.sewer_manhole_action.setCheckable(True)
        self.sewer_manhole_action.triggered.connect(
            self._toggle_sewer_manhole
        )
        self._sewer_manhole_configurator = (
            SewerManholeConfiguratorController(
                self.iface,
                self.sewer_manhole_action,
                self.refresh_state,
            )
        )
        self.sewer_pumping_station_action = self._add_tool_action(
            "Pumpla",
            "EVELSewerPumpingStationAction",
            ICON_PUMPING_STATION,
        )
        self.sewer_pumping_station_action.setCheckable(True)
        self.sewer_pumping_station_action.triggered.connect(
            self._toggle_sewer_pumping_station
        )
        self._sewer_pumping_station_configurator = (
            SewerPumpingStationConfiguratorController(
                self.iface,
                self.sewer_pumping_station_action,
                self.refresh_state,
            )
        )
        self.toolbar.addSeparator()
        self.import_action = self._add_tool_action(
            "Impordi",
            "EVELImportAction",
            ICON_IMPORT,
        )
        self.import_action.triggered.connect(self._open_importer)
        self.clear_data_action = self._add_tool_action(
            "Tühjenda",
            "EVELClearImportDataAction",
            ICON_CLEAR_DATA,
        )
        self.clear_data_action.triggered.connect(self._open_data_clearer)
        self.reverse_action = self._add_tool_action(
            "Pööra suund",
            "EVELReverseWaterDuctAction",
            ICON_REVERSE_FLOW,
        )
        self.reverse_action.setCheckable(True)
        self.reverse_action.triggered.connect(
            self._toggle_flow_direction
        )
        self._flow_direction_controller = FlowDirectionController(
            self.iface,
            self.reverse_action,
            self.refresh_state,
        )
        self.check_action = self._add_tool_action(
            "Kontrolli",
            "EVELCheckWaterNetworkAction",
            ICON_CHECK_NETWORK,
        )
        self.repair_action = self._add_tool_action(
            "Paranda",
            "EVELRepairWaterDuctAction",
            ICON_REPAIR_NETWORK,
        )

        for action in self._interactive_tool_actions():
            self._connect(action.toggled, self._on_tool_toggled)

        project = QgsProject.instance()
        self._connect(self.iface.currentLayerChanged, self.refresh_state)
        self._connect(project.readProject, self.refresh_state)
        self._connect(project.cleared, self.refresh_state)
        self._connect(project.layersAdded, self.refresh_state)
        self._connect(project.layersRemoved, self.refresh_state)
        self._connect(project.transactionModeChanged, self.refresh_state)

        self.refresh_state()

    def unload(self):
        if self._diagnostics_dialog is not None:
            self._diagnostics_dialog.close()
            self._diagnostics_dialog = None
        if self._import_dialog is not None:
            self._import_dialog.close()
            self._import_dialog = None
        if self._clear_data_dialog is not None:
            self._clear_data_dialog.close()
            self._clear_data_dialog = None
        if self._add_controller is not None:
            self._add_controller.cancel()
            self._add_controller = None
        if self._gravity_controller is not None:
            self._gravity_controller.cancel()
            self._gravity_controller = None
        if self._edit_duct_controller is not None:
            self._edit_duct_controller.cancel()
            self._edit_duct_controller = None
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
            self._flow_direction_controller = None
        if self._node_configurator is not None:
            self._node_configurator.cancel()
            self._node_configurator = None
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
            self._hydrant_configurator = None
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
            self._connection_point_configurator = None
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
            self._sewer_manhole_configurator = None
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
            self._sewer_pumping_station_configurator = None
        for signal, slot in reversed(self._connections):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()

        if self.toolbar is not None:
            self.toolbar.clear()
            self.toolbar.deleteLater()
            self.toolbar = None

        self.status_action = None
        self.status_menu = None
        self.add_duct_action = None
        self.add_duct_menu = None
        self.edit_duct_action = None
        self.configure_node_action = None
        self.hydrant_action = None
        self.connection_point_action = None
        self.sewer_manhole_action = None
        self.sewer_pumping_station_action = None
        self.import_action = None
        self.clear_data_action = None
        self.reverse_action = None
        self.check_action = None
        self.repair_action = None
        self._inspection = None
        self._duct_options = ()
        self._selected_duct_layer_id = ""
        self._sewer_manhole_ready = False
        self._hydrant_ready = False
        self._connection_point_ready = False
        self._sewer_pumping_station_ready = False
        self._import_ready = False
        self._import_reason = ""

    def refresh_state(self, *_args) -> None:
        """Re-evaluate the open project and update toolbar feedback."""

        project = QgsProject.instance()
        active_layer = self.iface.activeLayer()
        try:
            self._duct_options = self._duct_catalog.discover(project)
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            self._duct_options = ()
            QgsMessageLog.logMessage(
                f"Torukihtide kataloogi koostamine ebaõnnestus: {error}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
        try:
            self._inspection = self._resolve_project_water_inspection(
                project,
                active_layer,
            )
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            self._inspection = None
            QgsMessageLog.logMessage(
                f"Käivitusdiagnostika ebaõnnestus: {error}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
        self._sewer_manhole_ready = (
            self._sewer_manhole_inspector.is_available(project)
        )
        self._hydrant_ready = self._hydrant_inspector.is_available(project)
        self._connection_point_ready = (
            self._connection_point_inspector.is_available(project)
        )
        self._sewer_pumping_station_ready = (
            self._sewer_pumping_station_inspector.is_available(project)
        )
        self._import_ready, self._import_reason = (
            self._import_target_inspector.is_available(project)
        )

        self._rebuild_add_duct_menu()
        self._update_tool_actions()
        self._update_status_action()

    def _resolve_project_water_inspection(
        self,
        project: QgsProject,
        active_layer,
    ) -> ProjectInspection:
        """Resolve water topology from a pipe layer, not any active display layer."""

        water_options = tuple(
            option
            for option in self._duct_options
            if option.workflow is DuctWorkflow.WATER_TOPOLOGY
            and option.inspection is not None
        )
        active_id = active_layer.id() if active_layer is not None else ""
        active_option = next(
            (
                option
                for option in water_options
                if option.layer.id() == active_id
            ),
            None,
        )
        if active_option is not None:
            return active_option.inspection

        if self._is_usable_water_edge_candidate(active_layer):
            return self._inspector.inspect(project, active_layer)

        active_network_id = self._layer_default_int(
            active_layer,
            "NETWORK_ID",
        )
        matching_option = next(
            (
                option
                for option in water_options
                if option.enabled
                and option.network_id == active_network_id
            ),
            None,
        )
        if matching_option is not None:
            return matching_option.inspection

        enabled_option = next(
            (option for option in water_options if option.enabled),
            None,
        )
        if enabled_option is not None:
            return enabled_option.inspection

        option_by_layer_id = {
            option.layer.id(): option
            for option in water_options
        }
        first_project_inspection = None
        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if not self._is_usable_water_edge_candidate(layer):
                continue
            option = option_by_layer_id.get(layer.id())
            candidate = (
                option.inspection
                if option is not None
                else self._inspector.inspect(project, layer)
            )
            if first_project_inspection is None:
                first_project_inspection = candidate
            if candidate.can_add_water_duct:
                return candidate

        if water_options:
            return water_options[0].inspection
        if first_project_inspection is not None:
            return first_project_inspection

        return self._inspector.inspect(project, None)

    def show_diagnostics(self, *_args) -> None:
        """Open or refresh the copyable detailed diagnostics window."""

        self.refresh_state()
        report = self._diagnostics_report()
        status_text = self._status_headline()
        status_icon = (
            self.status_action.icon()
            if self.status_action is not None
            else catalog_icon(ICON_ERROR)
        )

        dialog = self._diagnostics_dialog
        if dialog is not None:
            try:
                dialog.set_report(report, status_text, status_icon)
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
                return
            except RuntimeError:
                self._diagnostics_dialog = None

        dialog = DiagnosticsDialog(
            report,
            status_text,
            status_icon,
            parent=self.iface.mainWindow(),
        )
        dialog.destroyed.connect(self._diagnostics_dialog_reference)
        self._diagnostics_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        has_error, has_warning, _message = self._status_details()
        if has_error:
            level = Qgis.MessageLevel.Critical
        elif has_warning:
            level = Qgis.MessageLevel.Warning
        else:
            level = Qgis.MessageLevel.Success
        QgsMessageLog.logMessage(report, MESSAGE_TAG, level)

    def _diagnostics_dialog_reference(self, *_args) -> None:
        self._diagnostics_dialog = None

    def _add_tool_action(
        self,
        text: str,
        object_name: str,
        icon_name: str,
    ) -> QAction:
        action = QAction(text, self.iface.mainWindow())
        set_catalog_icon(action, icon_name)
        action.setObjectName(object_name)
        action.setEnabled(False)
        action.setToolTip(f"{text}: tööriist on arendamisel.")
        self.toolbar.addAction(action)
        return action

    def _update_status_action(self) -> None:
        if self.status_action is None:
            return

        has_error, has_warning, message = self._status_details()
        if has_error:
            icon = catalog_icon(ICON_ERROR)
            fallback = QStyle.SP_MessageBoxCritical
        elif has_warning:
            icon = catalog_icon(ICON_STATUS_WARNING)
            fallback = QStyle.SP_MessageBoxWarning
        else:
            icon = catalog_icon(ICON_STATUS_OK)
            fallback = QStyle.SP_DialogApplyButton
        if icon.isNull():
            icon = QApplication.style().standardIcon(fallback)
        self.status_action.setIcon(icon)

        layer_label = self._active_layer_label()
        tool_name, guidance, compact_guidance = self._active_tool_guidance()
        if tool_name is not None:
            summary = (
                f"{tool_name} · {self._ellipsize(layer_label, 26)} — "
                f"{compact_guidance}"
            )
        elif has_error:
            summary = (
                f"EVEL · {self._ellipsize(layer_label, 30)} — "
                "vajab tähelepanu"
            )
        elif has_warning:
            summary = (
                f"EVEL · {self._ellipsize(layer_label, 30)} — "
                "kontrolli hoiatusi"
            )
        else:
            summary = f"EVEL · {self._ellipsize(layer_label, 34)} — vali tööriist"
        self.status_action.setText(summary)
        self.status_action.setToolTip(
            "EVEL Võrgutööriistad\n"
            f"Aktiivne kiht: {layer_label}\n"
            f"Tööriist: {tool_name or 'ükski kaarditööriist pole aktiivne'}\n"
            f"Järgmine samm: {guidance}\n"
            f"Olek: {message}\n"
            "Klõpsa olekupaneeli avamiseks."
        )
        self._rebuild_status_menu()
        self._update_open_diagnostics_dialog()

    def _status_details(self) -> tuple[bool, bool, str]:
        """Return the current project severity and its concise explanation."""

        active_option = self._active_duct_option()
        inspection = self._inspection
        if active_option is not None:
            has_error = not active_option.enabled
            has_warning = bool(
                active_option.inspection
                and active_option.inspection.warnings
                and not has_error
            )
            message = (
                f"Aktiivne torukiht „{active_option.label}“ on kasutatav."
                if active_option.enabled
                else active_option.reason
            )
            return has_error, has_warning, message

        usable = self._has_usable_workflow()
        if not usable:
            message = (
                inspection.short_message()
                if inspection is not None
                else "Käivitusdiagnostika ebaõnnestus."
            )
            return True, False, message

        if inspection is not None and inspection.errors:
            return (
                False,
                True,
                "Osa veevõrgu töövoogudest pole kasutatav: "
                + inspection.short_message(),
            )
        if inspection is not None and inspection.warnings:
            return False, True, inspection.short_message()

        active_layer = self.iface.activeLayer()
        if active_layer is None:
            message = "EVEL-i tööriistad on kasutatavad; aktiivset kihti pole."
        elif self._is_evel_project_layer(active_layer):
            message = (
                f"Aktiivne EVEL-i kiht „{self._active_layer_label()}“; "
                "tööriistad on kasutatavad."
            )
        else:
            message = (
                "EVEL-i tööriistad on kasutatavad; aktiivne kiht "
                f"„{self._active_layer_label()}“ ei ole EVEL-i projektikiht."
            )

        return False, False, message

    def _has_usable_workflow(self) -> bool:
        return bool(
            any(option.enabled for option in self._duct_options)
            or (
                self._inspection is not None
                and self._inspection.can_add_water_duct
            )
            or self._hydrant_ready
            or self._connection_point_ready
            or self._sewer_manhole_ready
            or self._sewer_pumping_station_ready
            or self._import_ready
        )

    @staticmethod
    def _is_water_edge_layer(layer) -> bool:
        if layer is None:
            return False
        role = str(layer.customProperty("evel_topology_role", "")).casefold()
        table = str(layer.customProperty("evel_project_table", "")).casefold()
        return role == "water_edge" or table == "sn_water_duct"

    @classmethod
    def _is_usable_water_edge_candidate(cls, layer) -> bool:
        if not cls._is_water_edge_layer(layer):
            return False
        component_key = str(
            layer.customProperty("evel_preview_checkbox", "")
        ).strip().casefold()
        if component_key == "cbwaterabandoned":
            return False
        return "REMOVAL_YEAR" not in layer.subsetString().upper()

    @staticmethod
    def _is_evel_project_layer(layer) -> bool:
        if layer is None:
            return False
        value = layer.customProperty("evel_project_layer", False)
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on"}

    @staticmethod
    def _layer_default_int(layer, field_name: str) -> int | None:
        if not isinstance(layer, QgsVectorLayer):
            return None
        field_index = layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        expression = layer.defaultValueDefinition(
            field_index
        ).expression().strip()
        if not expression:
            return None
        try:
            return int(expression.strip("'\""))
        except (TypeError, ValueError):
            return None

    def _status_headline(self) -> str:
        has_error, has_warning, _message = self._status_details()
        if has_error:
            return "EVEL vajab tähelepanu"
        if has_warning:
            return "EVEL on kasutatav hoiatustega"
        return "EVEL on valmis"

    def _tool_groups(self):
        """Return toolbar actions grouped by the user's network workflow."""

        return (
            (
                "Torud",
                (
                    self.add_duct_action,
                    self.edit_duct_action,
                    self.reverse_action,
                ),
            ),
            (
                "Sõlmed ja rajatised",
                (
                    self.configure_node_action,
                    self.hydrant_action,
                    self.connection_point_action,
                    self.sewer_manhole_action,
                    self.sewer_pumping_station_action,
                ),
            ),
            (
                "Andmed",
                (self.import_action, self.clear_data_action),
            ),
            (
                "Kontroll",
                (self.check_action, self.repair_action),
            ),
        )

    def _interactive_tool_actions(self) -> tuple[QAction, ...]:
        """Return actions which represent an active map interaction."""

        return tuple(
            action
            for action in (
                self.add_duct_action,
                self.edit_duct_action,
                self.configure_node_action,
                self.hydrant_action,
                self.connection_point_action,
                self.sewer_manhole_action,
                self.sewer_pumping_station_action,
                self.reverse_action,
            )
            if action is not None
        )

    def _active_layer_label(self) -> str:
        layer = self.iface.activeLayer()
        if layer is None:
            return "kiht puudub"
        try:
            return layer.name() or "nimetu kiht"
        except RuntimeError:
            return "kiht pole enam saadaval"

    def _active_tool_guidance(self) -> tuple[str | None, str, str]:
        guidance_by_action = (
            (
                self.add_duct_action,
                "Klõpsa kaardil toru alguspunktil ja jätka joonestamist.",
                "klõpsa alguspunktil",
            ),
            (
                self.edit_duct_action,
                "Klõpsa kaardil olemasoleval EVEL-i torul.",
                "klõpsa torul",
            ),
            (
                self.configure_node_action,
                "Klõpsa kaardil veesõlmel, mida soovid konfigureerida.",
                "klõpsa veesõlmel",
            ),
            (
                self.hydrant_action,
                "Klõpsa hüdrandil, veesõlmel või veetorul.",
                "klõpsa objektil",
            ),
            (
                self.connection_point_action,
                "Klõpsa liitumispunktil või vee-/kanalisatsioonisõlmel.",
                "klõpsa punktil või sõlmel",
            ),
            (
                self.sewer_manhole_action,
                "Klõpsa isevoolsel torul või kanalisatsioonisõlmel.",
                "klõpsa torul või sõlmel",
            ),
            (
                self.sewer_pumping_station_action,
                "Klõpsa kanalisatsioonitorul või -sõlmel.",
                "klõpsa torul või sõlmel",
            ),
            (
                self.reverse_action,
                "Klõpsa torul voolusuuna määramiseks või pööramiseks.",
                "klõpsa torul",
            ),
        )
        for action, guidance, compact_guidance in guidance_by_action:
            if action is not None and action.isChecked():
                return action.text(), guidance, compact_guidance

        ready = any(
            action is not None and action.isEnabled()
            for _group, actions in self._tool_groups()
            for action in actions
        )
        if ready:
            return None, "Vali sobiv tööriist.", "vali tööriist"
        if self.iface.activeLayer() is None:
            return (
                None,
                "Ava EVEL-i projekt või vali toetatud võrgukiht.",
                "vali võrgukiht",
            )
        if self._inspection is not None:
            return (
                None,
                self._inspection.short_message(),
                "kontrolli projekti",
            )
        return None, "Kontrolli projekti valmisolekut.", "kontrolli projekti"

    @staticmethod
    def _ellipsize(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 1)].rstrip() + "…"

    @staticmethod
    def _tool_reason(action: QAction) -> str:
        lines = [line.strip() for line in action.toolTip().splitlines()]
        lines = [line for line in lines if line]
        if lines and lines[0].rstrip(":") == action.text().rstrip(":"):
            lines = lines[1:]
        return " ".join(lines) or (
            "Tööriist on kasutatav."
            if action.isEnabled()
            else "Tööriist ei ole praeguses projektikontekstis kasutatav."
        )

    def _diagnostics_report(self) -> str:
        """Build a complete plain-text snapshot without exposing data sources."""

        project = QgsProject.instance()
        has_error, has_warning, message = self._status_details()
        tool_name, guidance, _compact = self._active_tool_guidance()
        project_title = project.title().strip() or "pealkiri puudub"
        project_file = project.fileName().strip() or "salvestamata projekt"
        severity = (
            "VIGA" if has_error else "HOIATUS" if has_warning else "VALMIS"
        )
        lines = [
            "EVEL VÕRGUTÖÖRIISTADE DIAGNOSTIKA",
            "=================================",
            f"Olek: {severity} — {self._status_headline()}",
            f"Kokkuvõte: {message}",
            f"Projekt: {project_title}",
            f"Projektifail: {project_file}",
            f"Aktiivne kiht: {self._active_layer_label()}",
            (
                "Aktiivne tööriist: "
                + (tool_name or "ükski kaarditööriist pole aktiivne")
            ),
            f"Järgmine samm: {guidance}",
            "",
            "PROJEKTIDIAGNOSTIKA",
            "--------------------",
        ]

        inspection = self._inspection
        if inspection is None:
            lines.append("Käivitusdiagnostikat ei õnnestunud koostada.")
        elif not inspection.diagnostics:
            lines.append("Diagnostikakirjeid pole.")
        else:
            level_labels = {
                "error": "VIGA",
                "warning": "HOIATUS",
                "info": "INFO",
            }
            for item in inspection.diagnostics:
                level_label = level_labels.get(
                    item.level.value,
                    item.level.value.upper(),
                )
                lines.append(f"[{level_label}] {item.code}")
                lines.append(f"  {item.message}")
                if item.layer_id:
                    lines.append(f"  Kihi ID: {item.layer_id}")
                lines.append("")
            if lines[-1] == "":
                lines.pop()

        lines.extend(
            [
                "",
                "TORUKIHTIDE VALIKUD",
                "-------------------",
            ]
        )
        if not self._duct_options:
            lines.append("Toetatud torukihte ei leitud.")
        else:
            workflow_labels = {
                DuctWorkflow.WATER_TOPOLOGY: "vee topoloogia",
                DuctWorkflow.GRAVITY_GEOMETRY: "isevoolne geomeetria",
            }
            for option in self._duct_options:
                state = "VALMIS" if option.enabled else "POLE SAADAVAL"
                lines.append(f"[{state}] {option.label}")
                lines.append(
                    "  Töövoog: "
                    + workflow_labels.get(option.workflow, option.workflow.value)
                )
                lines.append(f"  Võrgu ID: {option.network_id}")
                lines.append(f"  Võrgutüübi ID: {option.nettype_id}")
                lines.append(f"  Põhjus: {option.reason or '—'}")

        lines.extend(
            [
                "",
                "TÖÖRIISTADE VALMISOLEK",
                "----------------------",
            ]
        )
        for group_name, actions in self._tool_groups():
            lines.append(group_name.upper())
            for action in actions:
                if action is None:
                    continue
                state = "VALMIS" if action.isEnabled() else "POLE SAADAVAL"
                lines.append(f"  [{state}] {action.text()}")
                lines.append(f"    {self._tool_reason(action)}")

        return "\n".join(lines).rstrip() + "\n"

    def _update_open_diagnostics_dialog(self) -> None:
        dialog = self._diagnostics_dialog
        if dialog is None or self.status_action is None:
            return
        try:
            dialog.set_report(
                self._diagnostics_report(),
                self._status_headline(),
                self.status_action.icon(),
            )
        except RuntimeError:
            self._diagnostics_dialog = None

    def _rebuild_status_menu(self) -> None:
        menu = self.status_menu
        if menu is None or self.status_action is None:
            return
        menu.clear()

        _has_error, _has_warning, message = self._status_details()
        headline = self._status_headline()
        headline_action = menu.addAction(self.status_action.icon(), headline)
        headline_action.setToolTip(message)
        headline_action.triggered.connect(self.show_diagnostics)

        layer_label = self._active_layer_label()
        tool_name, guidance, _compact_guidance = self._active_tool_guidance()
        context_lines = (
            (f"Aktiivne kiht: {self._ellipsize(layer_label, 64)}", layer_label),
            (
                "Tööriist: "
                + (tool_name or "ükski kaarditööriist pole aktiivne"),
                tool_name or "Ükski kaarditööriist pole aktiivne.",
            ),
            (
                f"Järgmine samm: {self._ellipsize(guidance, 84)}",
                guidance,
            ),
        )
        for text, tooltip in context_lines:
            context_action = menu.addAction(text)
            context_action.setEnabled(False)
            context_action.setToolTip(tooltip)

        menu.addSeparator()
        readiness_menu = menu.addMenu("Tööriistade valmisolek")
        readiness_menu.setObjectName("EVELStatusToolsMenu")
        readiness_menu.setToolTipsVisible(True)
        readiness_menu.setIcon(catalog_icon(ICON_CHECK_NETWORK))
        apply_evel_toolbar_light_style(None, readiness_menu)
        for group_name, actions in self._tool_groups():
            readiness_menu.addSection(group_name)
            for action in actions:
                if action is None:
                    continue
                enabled = action.isEnabled()
                reason = self._tool_reason(action)
                state = "valmis" if enabled else "pole saadaval"
                status_item = readiness_menu.addAction(
                    catalog_icon(
                        ICON_STATUS_OK if enabled else ICON_STATUS_WARNING
                    ),
                    f"{action.text()} — {state}",
                )
                status_item.setToolTip(reason)
                status_item.setStatusTip(reason)
                status_item.triggered.connect(
                    lambda _checked=False,
                    title=action.text(),
                    detail=reason,
                    ready=enabled: self._show_tool_readiness(
                        title, detail, ready
                    )
                )

        menu.addSeparator()
        refresh_action = menu.addAction("Värskenda olekut")
        set_catalog_icon(refresh_action, ICON_REFRESH)
        refresh_action.triggered.connect(self.refresh_state)
        diagnostics_action = menu.addAction("Ava detailne diagnostika…")
        diagnostics_action.setIcon(self.status_action.icon())
        diagnostics_action.triggered.connect(self.show_diagnostics)

    def _show_tool_readiness(
        self,
        title: str,
        detail: str,
        ready: bool,
    ) -> None:
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"{title}: {detail}",
            level=(
                Qgis.MessageLevel.Success
                if ready
                else Qgis.MessageLevel.Info
            ),
            duration=8,
        )

    def _on_tool_toggled(self, _checked: bool) -> None:
        self._update_status_action()

    def _update_tool_actions(self) -> None:
        """Enable tools whose implementation and project preflight are ready."""

        inspection = self._inspection
        water_ready = bool(inspection and inspection.can_add_water_duct)
        duct_ready = any(option.enabled for option in self._duct_options)
        if self.add_duct_action is not None:
            if duct_ready:
                reason = (
                    "Vali rippmenüüst toru liik. Valitud projektikiht "
                    "aktiveeritakse ja joonestamine käivitub."
                )
            else:
                reason = next(
                    (
                        option.reason
                        for option in self._duct_options
                        if option.reason
                    ),
                    "Projektis ei leitud ühtegi kasutatavat EVEL-i torukihti.",
                )
            self.add_duct_action.setEnabled(duct_ready)
            self.add_duct_action.setToolTip(f"Lisa toru\n{reason}")

        if self.configure_node_action is not None:
            if water_ready:
                reason = (
                    "Vali kaardilt veesõlm ning määra liitmik, rajatis, kaev "
                    "ja toruharude sulgeseadmed interaktiivsel skeemil."
                )
            else:
                reason = (
                    inspection.short_message()
                    if inspection is not None
                    else "Käivitusdiagnostika ebaõnnestus."
                )
            self.configure_node_action.setEnabled(water_ready)
            self.configure_node_action.setToolTip(
                f"Konfigureeri sõlm\n{reason}"
            )
        if self.edit_duct_action is not None:
            edit_ready = bool(self._duct_options)
            self.edit_duct_action.setEnabled(edit_ready)
            self.edit_duct_action.setToolTip(
                "Klõpsa olemasoleval EVEL-i torul ning vaata või muuda "
                "selle atribuute. Tehnilised ID-d ja geomeetria on lukus."
                if edit_ready
                else "Projektis puuduvad toetatud EVEL-i torukihid."
            )

        if self.hydrant_action is not None:
            self.hydrant_action.setEnabled(self._hydrant_ready)
            reason = (
                "Klõpsa olemasoleval hüdrandil või veesõlmel andmete "
                "muutmiseks. Veetorul klõpsates lisatakse uus hüdrant ja "
                "vajadusel poolitatakse toru."
                if self._hydrant_ready
                else "Projektis puudub Hüdrandid kiht, sn_fire_plug "
                "detailkiht või filtreerimata veesõlmede baaskiht."
            )
            self.hydrant_action.setToolTip(f"Hüdrant\n{reason}")

        if self.connection_point_action is not None:
            self.connection_point_action.setEnabled(
                self._connection_point_ready
            )
            reason = (
                "Klõpsa olemasoleval liitumispunktil andmete muutmiseks "
                "või olemasoleval vee-/kanalisatsioonisõlmel uue "
                "liitumispunkti loomiseks."
                if self._connection_point_ready
                else "Projektis puudub Liitumispunktid kiht või "
                "filtreerimata vee-/kanalisatsioonisõlmede baaskiht."
            )
            self.connection_point_action.setToolTip(
                f"Liitumispunkt\n{reason}"
            )

        if self.sewer_manhole_action is not None:
            self.sewer_manhole_action.setEnabled(
                self._sewer_manhole_ready
            )
            reason = (
                "Klõpsa isevoolsel torul või kanalisatsioonisõlmel. "
                "Sõlmeskeem lubab lisada kaevu või põlve/ühenduskoha "
                "ning kuvab torude tegelikud suunad ja kõrgused."
                if self._sewer_manhole_ready
                else "Projektis puuduvad kanalisatsiooni sõlme-, detail- "
                "või isevoolse toru kihid."
            )
            self.sewer_manhole_action.setToolTip(
                f"Kaev / põlv\n{reason}"
            )

        if self.sewer_pumping_station_action is not None:
            self.sewer_pumping_station_action.setEnabled(
                self._sewer_pumping_station_ready
            )
            reason = (
                "Klõpsa reovee-, sademevee- või drenaažitorul või "
                "kanalisatsioonisõlmel. Pumpla andmed avanevad eraldi "
                "mitmeosalises sisestusaknas."
                if self._sewer_pumping_station_ready
                else "Projektis puudub kasutatav kanalisatsiooni Pumplad "
                "kiht või sn_sewer_pumping_station detailkiht. "
                "Tööriist kontrollib käivitamisel ka sn_sewer_pump tabelit."
            )
            self.sewer_pumping_station_action.setToolTip(
                f"Pumpla\n{reason}"
            )

        if self.import_action is not None:
            self.import_action.setEnabled(self._import_ready)
            self.import_action.setToolTip(
                "Impordi EVEL-i kontrollpakett\n" + self._import_reason
            )
        if self.clear_data_action is not None:
            self.clear_data_action.setEnabled(self._import_ready)
            self.clear_data_action.setToolTip(
                "Tühjenda EVEL-i impordi üheksa sihttabelit\n"
                + self._import_reason
            )

        if self.reverse_action is not None:
            direction_ready = bool(
                FlowDirectionController.usable_options(
                    self._duct_options
                )
            )
            self.reverse_action.setEnabled(direction_ready)
            self.reverse_action.setToolTip(
                "Klõpsa torul suuna määramiseks või pööramiseks. "
                "Määramata suunaks saab joone algusest lõppu."
                if direction_ready
                else "Projektis puudub muudetava FLOWDIRECTION väljaga "
                "kasutatav torukiht."
            )

        for action in (self.check_action, self.repair_action):
            if action is not None:
                action.setEnabled(False)
                action.setToolTip(
                    f"{action.text()}: tööriist lisatakse järgmistes "
                    "arendusetappides."
                )

    def _toggle_add_duct(self, checked: bool) -> None:
        """Compatibility entry point for programmatic action triggering."""

        if self.add_duct_action is None:
            return
        if not checked:
            self._cancel_add_controllers()
            return

        self.refresh_state()
        option = self._active_duct_option()
        if option is None or not option.enabled:
            self.add_duct_action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Vali toru liik nupu „Lisa toru“ rippmenüüst.",
                level=Qgis.MessageLevel.Info,
                duration=5,
            )
            return
        self._activate_duct_option(option)

    def _rebuild_add_duct_menu(self) -> None:
        menu = self.add_duct_menu
        if menu is None:
            return
        menu.clear()

        groups = (
            (
                "Veetorud",
                DuctWorkflow.WATER_TOPOLOGY,
            ),
            (
                "Isevoolsed torud",
                DuctWorkflow.GRAVITY_GEOMETRY,
            ),
        )
        has_entries = False
        for title, workflow in groups:
            options = tuple(
                option
                for option in self._duct_options
                if option.workflow is workflow
            )
            if not options:
                continue
            menu.addSection(title)
            has_entries = True
            for option in options:
                action = menu.addAction(option.label)
                action.setObjectName(
                    f"EVELAddDuctLayer_{option.layer.id()}"
                )
                action.setCheckable(True)
                action.setChecked(
                    option.layer.id() == self._selected_duct_layer_id
                )
                action.setEnabled(option.enabled)
                action.setToolTip(option.reason)
                action.setStatusTip(option.reason)
                action.triggered.connect(
                    lambda _checked=False, selected=option: (
                        self._activate_duct_option(selected)
                    )
                )

        if not has_entries:
            empty_action = menu.addAction(
                "Projektis puuduvad toetatud torukihid"
            )
            empty_action.setEnabled(False)
        else:
            menu.addSeparator()
            coordinate_action = menu.addAction(
                "Lisa toru koordinaatidega…"
            )
            coordinate_action.setObjectName("EVELAddDuctCoordinatesAction")
            set_catalog_icon(coordinate_action, ICON_COORDINATE_DUCT)
            coordinate_action.setEnabled(
                any(option.enabled for option in self._duct_options)
            )
            coordinate_action.setToolTip(
                "Sisesta toru algus-, lõpp- ja võimalikud murdepunktid "
                "koordinaatidena."
            )
            coordinate_action.triggered.connect(
                self._open_coordinate_duct_dialog
            )

    def _activate_duct_option(self, option: DuctLayerOption) -> None:
        if self.add_duct_action is None or not option.enabled:
            return
        project_layer = QgsProject.instance().mapLayer(option.layer.id())
        if project_layer is not option.layer:
            self.refresh_state()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()

        self._selected_duct_layer_id = option.layer.id()
        self.iface.setActiveLayer(option.layer)

        activated = False
        if option.workflow is DuctWorkflow.WATER_TOPOLOGY:
            inspection = self._inspector.inspect(
                QgsProject.instance(),
                option.layer,
            )
            self._inspection = inspection
            if (
                inspection.can_add_water_duct
                and self._add_controller is not None
            ):
                activated = self._add_controller.activate(inspection)
            elif not inspection.can_add_water_duct:
                self.show_diagnostics()
        elif self._gravity_controller is not None:
            activated = self._gravity_controller.activate(option.layer)

        if not activated:
            self.add_duct_action.setChecked(False)
        self._rebuild_add_duct_menu()

    def _open_coordinate_duct_dialog(self) -> None:
        options = tuple(option for option in self._duct_options if option.enabled)
        if not options:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Projektis puuduvad koordinaatidega lisatavad torukihid.",
                level=Qgis.MessageLevel.Warning,
                duration=6,
            )
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._edit_duct_controller is not None:
            self._edit_duct_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()

        selected_id = self._selected_duct_layer_id
        active = self._active_duct_option()
        if not selected_id and active is not None:
            selected_id = active.layer.id()
        try:
            dialog = CoordinateDuctDialog(
                options,
                selected_layer_id=selected_id,
                project_crs=QgsProject.instance().crs(),
                parent=self.iface.mainWindow(),
            )
        except CoordinateDuctInputError as error:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                str(error),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if dialog.exec_() != QDialog.Accepted:
            return

        option = dialog.selected_option
        project_layer = QgsProject.instance().mapLayer(option.layer.id())
        if project_layer is not option.layer:
            self.refresh_state()
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Valitud torukiht ei ole enam projektis saadaval.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        try:
            geometry = dialog.duct_geometry()
        except CoordinateDuctInputError as error:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                str(error),
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return

        self._selected_duct_layer_id = option.layer.id()
        self.iface.setActiveLayer(option.layer)
        if option.workflow is DuctWorkflow.WATER_TOPOLOGY:
            inspection = self._inspector.inspect(
                QgsProject.instance(),
                option.layer,
            )
            self._inspection = inspection
            if self._add_controller is not None:
                self._add_controller.add_geometry(inspection, geometry)
        elif self._gravity_controller is not None:
            self._gravity_controller.add_geometry(option.layer, geometry)
        self.refresh_state()

    def _cancel_add_controllers(self) -> None:
        if self._add_controller is not None:
            self._add_controller.cancel()
        if self._gravity_controller is not None:
            self._gravity_controller.cancel()

    def _toggle_edit_duct(self, checked: bool) -> None:
        controller = self._edit_duct_controller
        action = self.edit_duct_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        self.refresh_state()
        if not self._duct_options or not controller.activate(
            self._duct_options
        ):
            action.setChecked(False)

    def _toggle_flow_direction(self, checked: bool) -> None:
        controller = self._flow_direction_controller
        action = self.reverse_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._edit_duct_controller is not None:
            self._edit_duct_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        self.refresh_state()
        if not controller.activate(self._duct_options):
            action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Projektis puudub muudetava FLOWDIRECTION väljaga "
                "kasutatav torukiht.",
                level=Qgis.MessageLevel.Critical,
                duration=7,
            )

    def _toggle_sewer_manhole(self, checked: bool) -> None:
        controller = self._sewer_manhole_configurator
        action = self.sewer_manhole_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        self.refresh_state()
        if not self._sewer_manhole_ready:
            action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Kanalisatsioonisõlme jaoks vajalikud generaatori kihid "
                "puuduvad.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if not controller.activate():
            action.setChecked(False)

    def _toggle_sewer_pumping_station(self, checked: bool) -> None:
        controller = self._sewer_pumping_station_configurator
        action = self.sewer_pumping_station_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        self.refresh_state()
        if not self._sewer_pumping_station_ready:
            action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Kanalisatsioonipumpla jaoks vajalikud generaatori kihid "
                "või pumbatabel puuduvad.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if not controller.activate():
            action.setChecked(False)

    def _open_importer(self) -> None:
        """Open the GeoPackage importer for the active EVEL project."""

        self.refresh_state()
        if not self._import_ready:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                self._import_reason or "Projekt ei sobi EVEL-i impordiks.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if self._import_dialog is not None:
            self._import_dialog.show()
            self._import_dialog.raise_()
            self._import_dialog.activateWindow()
            return
        dialog = EvelImportDialog(
            QgsProject.instance(),
            self.iface.mainWindow(),
        )
        dialog.import_completed.connect(self._on_import_completed)
        dialog.destroyed.connect(self._clear_import_dialog)
        self._import_dialog = dialog
        dialog.show()

    def _clear_import_dialog(self, *_args) -> None:
        self._import_dialog = None

    def _open_data_clearer(self) -> None:
        """Open the guarded importer-target clearing tool."""

        self.refresh_state()
        if not self._import_ready:
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                self._import_reason
                or "Projekt ei sobi EVEL-i andmete tühjendamiseks.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if self._clear_data_dialog is not None:
            self._clear_data_dialog.show()
            self._clear_data_dialog.raise_()
            self._clear_data_dialog.activateWindow()
            return
        dialog = EvelClearDataDialog(
            QgsProject.instance(),
            self.iface.mainWindow(),
        )
        dialog.clear_completed.connect(self._on_clear_completed)
        dialog.destroyed.connect(self._clear_data_dialog_reference)
        self._clear_data_dialog = dialog
        dialog.show()

    def _clear_data_dialog_reference(self, *_args) -> None:
        self._clear_data_dialog = None

    def _on_clear_completed(self, result) -> None:
        self._reload_postgres_layers()
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Tühjendamine lõpetatud: {result.total_count:,} kirjet "
            "kustutati ühe tehinguna.",
            level=Qgis.MessageLevel.Success,
            duration=10,
        )
        self.refresh_state()

    def _on_import_completed(self, _plan, result) -> None:
        """Refresh every project view backed by an imported EVEL table."""

        self._reload_postgres_layers()
        self.iface.messageBar().pushMessage(
            MESSAGE_TAG,
            f"Import lõpetatud: {result.total_count:,} kirjet lisati "
            "ühe tehinguna.",
            level=Qgis.MessageLevel.Success,
            duration=10,
        )
        self.refresh_state()

    def _reload_postgres_layers(self) -> None:
        """Reload project views after a direct SQL transaction."""

        project = QgsProject.instance()
        for layer in project.mapLayers().values():
            if layer.providerType() != "postgres":
                continue
            try:
                layer.reload()
                layer.triggerRepaint()
            except (AttributeError, RuntimeError):
                continue
        self.iface.mapCanvas().refresh()

    def _active_duct_option(self) -> DuctLayerOption | None:
        active_layer = self.iface.activeLayer()
        active_id = active_layer.id() if active_layer is not None else ""
        return next(
            (
                option
                for option in self._duct_options
                if option.layer.id() == active_id
            ),
            None,
        )

    def _toggle_configure_node(self, checked: bool) -> None:
        controller = self._node_configurator
        if controller is None or self.configure_node_action is None:
            return
        if not checked:
            controller.cancel()
            return

        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        self.refresh_state()
        inspection = self._inspection
        if inspection is None or not inspection.can_add_water_duct:
            self.configure_node_action.setChecked(False)
            self.show_diagnostics()
            return
        if not controller.activate(inspection):
            self.configure_node_action.setChecked(False)

    def _toggle_hydrant(self, checked: bool) -> None:
        controller = self._hydrant_configurator
        action = self.hydrant_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._edit_duct_controller is not None:
            self._edit_duct_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._connection_point_configurator is not None:
            self._connection_point_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        self.refresh_state()
        if not self._hydrant_ready:
            action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Hüdrandi jaoks vajalikud generaatori sõlme- ja "
                "detailkihid puuduvad.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if not controller.activate():
            action.setChecked(False)

    def _toggle_connection_point(self, checked: bool) -> None:
        controller = self._connection_point_configurator
        action = self.connection_point_action
        if controller is None or action is None:
            return
        if not checked:
            controller.cancel()
            return

        self._cancel_add_controllers()
        if self._flow_direction_controller is not None:
            self._flow_direction_controller.cancel()
        if self._edit_duct_controller is not None:
            self._edit_duct_controller.cancel()
        if self._node_configurator is not None:
            self._node_configurator.cancel()
        if self._hydrant_configurator is not None:
            self._hydrant_configurator.cancel()
        if self._sewer_manhole_configurator is not None:
            self._sewer_manhole_configurator.cancel()
        if self._sewer_pumping_station_configurator is not None:
            self._sewer_pumping_station_configurator.cancel()
        self.refresh_state()
        if not self._connection_point_ready:
            action.setChecked(False)
            self.iface.messageBar().pushMessage(
                MESSAGE_TAG,
                "Liitumispunktide jaoks vajalik kiht või filtreerimata "
                "võrgusõlmede baaskiht puudub.",
                level=Qgis.MessageLevel.Critical,
                duration=8,
            )
            return
        if not controller.activate():
            action.setChecked(False)

    def _connect(self, signal, slot) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))
