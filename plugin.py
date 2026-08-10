"""QGIS plugin lifecycle and the persistent EVEL toolbar."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QAction,
    QApplication,
    QMenu,
    QStyle,
    QToolButton,
)
from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject

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
    EvelClearDataDialog,
    EvelImportDialog,
    VisualNodeConfiguratorDialog,
)
from .ui.light_style import apply_evel_toolbar_light_style


MESSAGE_TAG = "EVEL Võrgutööriistad"
TOOLBAR_OBJECT_NAME = "EVELNetworkToolsToolbar"


class EVELNetworkToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.toolbar = None
        self.status_action = None
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

        self.status_action = QAction("EVEL", self.iface.mainWindow())
        self.status_action.setObjectName("EVELNetworkStatusAction")
        self.status_action.triggered.connect(self.show_diagnostics)
        self.toolbar.addAction(self.status_action)
        self.toolbar.addSeparator()

        self.add_duct_action = self._add_tool_action(
            "Lisa toru",
            "/mActionAddFeature.svg",
            "EVELAddDuctAction",
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
            "/mActionIdentify.svg",
            "EVELEditDuctAction",
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
            "/mActionMapTips.svg",
            "EVELConfigureWaterNodeAction",
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
            "/mActionAddPoint.svg",
            "EVELHydrantAction",
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
            "/mActionAddPoint.svg",
            "EVELConnectionPointAction",
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
            "/mActionAddPoint.svg",
            "EVELSewerManholeClockAction",
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
            "/mActionAddPoint.svg",
            "EVELSewerPumpingStationAction",
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
            "/mActionFileOpen.svg",
            "EVELImportAction",
        )
        self.import_action.triggered.connect(self._open_importer)
        self.clear_data_action = self._add_tool_action(
            "Tühjenda",
            "/mActionDeleteSelected.svg",
            "EVELClearImportDataAction",
        )
        self.clear_data_action.triggered.connect(self._open_data_clearer)
        self.reverse_action = self._add_tool_action(
            "Pööra suund",
            "/mActionReverseLine.svg",
            "EVELReverseWaterDuctAction",
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
            "/mActionCheckGeometry.svg",
            "EVELCheckWaterNetworkAction",
        )
        self.repair_action = self._add_tool_action(
            "Paranda",
            "/mActionRefresh.svg",
            "EVELRepairWaterDuctAction",
        )

        project = QgsProject.instance()
        self._connect(self.iface.currentLayerChanged, self.refresh_state)
        self._connect(project.readProject, self.refresh_state)
        self._connect(project.cleared, self.refresh_state)
        self._connect(project.layersAdded, self.refresh_state)
        self._connect(project.layersRemoved, self.refresh_state)
        self._connect(project.transactionModeChanged, self.refresh_state)

        self.refresh_state()

    def unload(self):
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
        try:
            self._inspection = self._inspector.inspect(
                project, self.iface.activeLayer()
            )
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            self._inspection = None
            QgsMessageLog.logMessage(
                f"Käivitusdiagnostika ebaõnnestus: {error}",
                MESSAGE_TAG,
                Qgis.MessageLevel.Critical,
            )
        try:
            self._duct_options = self._duct_catalog.discover(project)
        except Exception as error:  # pragma: no cover - QGIS runtime guard
            self._duct_options = ()
            QgsMessageLog.logMessage(
                f"Torukihtide kataloogi koostamine ebaõnnestus: {error}",
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
        self._update_status_action()
        self._update_tool_actions()

    def show_diagnostics(self) -> None:
        """Show the current preflight result without changing the project."""

        active_option = self._active_duct_option()
        inspection = self._inspection
        if (
            active_option is not None
            and active_option.workflow is DuctWorkflow.GRAVITY_GEOMETRY
        ):
            message = (
                f"Aktiivne torukiht „{active_option.label}“ on kasutatav."
                if active_option.enabled
                else active_option.reason
            )
            level = (
                Qgis.MessageLevel.Success
                if active_option.enabled
                else Qgis.MessageLevel.Critical
            )
        elif inspection is None:
            message = "Käivitusdiagnostikat ei õnnestunud koostada."
            level = Qgis.MessageLevel.Critical
        elif inspection.errors:
            message = inspection.short_message()
            level = Qgis.MessageLevel.Critical
        elif inspection.warnings:
            message = inspection.short_message()
            level = Qgis.MessageLevel.Warning
        else:
            message = inspection.short_message()
            level = Qgis.MessageLevel.Success

        self.iface.messageBar().pushMessage(
            MESSAGE_TAG, message, level=level, duration=8
        )

        if inspection is not None and inspection.diagnostics:
            details = "\n".join(
                f"[{item.level.value}] {item.code}: {item.message}"
                for item in inspection.diagnostics
            )
            QgsMessageLog.logMessage(details, MESSAGE_TAG, level)

    def _add_tool_action(
        self, text: str, theme_icon: str, object_name: str
    ) -> QAction:
        action = QAction(
            QgsApplication.getThemeIcon(theme_icon),
            text,
            self.iface.mainWindow(),
        )
        action.setObjectName(object_name)
        action.setEnabled(False)
        action.setToolTip(f"{text}: tööriist on arendamisel.")
        self.toolbar.addAction(action)
        return action

    def _update_status_action(self) -> None:
        if self.status_action is None:
            return

        style = QApplication.style()
        active_option = self._active_duct_option()
        inspection = self._inspection
        if (
            active_option is not None
            and active_option.workflow is DuctWorkflow.GRAVITY_GEOMETRY
        ):
            has_error = not active_option.enabled
            has_warning = False
            message = (
                f"Aktiivne torukiht „{active_option.label}“ on kasutatav."
                if active_option.enabled
                else active_option.reason
            )
        else:
            has_error = inspection is None or bool(inspection.errors)
            has_warning = bool(inspection and inspection.warnings)
            message = (
                inspection.short_message()
                if inspection is not None
                else "Käivitusdiagnostika ebaõnnestus."
            )

        if has_error:
            icon = style.standardIcon(QStyle.SP_MessageBoxCritical)
        elif has_warning:
            icon = style.standardIcon(QStyle.SP_MessageBoxWarning)
        else:
            icon = style.standardIcon(QStyle.SP_DialogApplyButton)
        self.status_action.setIcon(icon)

        self.status_action.setToolTip(
            f"EVEL Võrgutööriistad\n{message}\nKlõpsa diagnostika kuvamiseks."
        )

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
