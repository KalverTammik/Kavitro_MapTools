"""QGIS entry point for EVEL Network Tools."""


def classFactory(iface):  # noqa: N802 - QGIS plugin API name
    from .plugin import EVELNetworkToolsPlugin

    return EVELNetworkToolsPlugin(iface)
