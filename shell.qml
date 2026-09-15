//@ pragma UseQApplication
//@ pragma ShellId ambxst+
//@ pragma DataDir $BASE/ambxst+
//@ pragma StateDir $BASE/ambxst+

import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.modules.bar
import qs.modules.bar.workspaces
import qs.modules.notifications

import qs.modules.notch
import qs.modules.services
import qs.modules.corners
import qs.modules.frame
import qs.modules.components
import qs.modules.lockscreen
import qs.modules.dock
import qs.modules.globals
import qs.modules.shell
// Sidebar + assistant modules must be registered in the shell tree so the
// deferred Loader.source overlays can import them. Instantiation stays lazy
// (Loader.active); only the module URI is registered at startup.
import qs.modules.sidebar
import qs.modules.widgets.assistant
import qs.config

ShellRoot {
    id: root

    function _sourceMatches(loader, url) {
        return String(loader.source || "").indexOf(url) !== -1;
    }

    function _loadScreenItem(loader, url, screen) {
        if (!loader.active) {
            if (loader.source)
                loader.source = "";
            return;
        }
        if (root._sourceMatches(loader, url))
            return;
        loader.setSource(url, { "screen": screen });
    }

    function _loadNamedItem(loader, url, propName, value) {
        if (!loader.active) {
            if (loader.source)
                loader.source = "";
            return;
        }
        if (root._sourceMatches(loader, url))
            return;
        const props = {};
        props[propName] = value;
        loader.setSource(url, props);
    }

    Component.onCompleted: {
        console.log("ambxst+: shell initialized (version", Config.version + ")");
    }

    ContextMenu {
        id: contextMenu
        screen: Quickshell.screens[0]
        Component.onCompleted: Visibilities.setContextMenu(contextMenu)
    }

    Variants {
        model: Quickshell.screens

        Loader {
            id: wallpaperLoader
            active: true
            asynchronous: true
            required property ShellScreen modelData
            onActiveChanged: root._loadScreenItem(wallpaperLoader, "modules/widgets/dashboard/wallpapers/Wallpaper.qml", modelData)
            Component.onCompleted: root._loadScreenItem(wallpaperLoader, "modules/widgets/dashboard/wallpapers/Wallpaper.qml", modelData)
        }
    }

    Variants {
        model: Quickshell.screens

        Loader {
            id: desktopLoader
            active: Config.desktop.enabled && SuspendManager.wakeReady
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadScreenItem(desktopLoader, "modules/desktop/Desktop.qml", modelData)
            Component.onCompleted: root._loadScreenItem(desktopLoader, "modules/desktop/Desktop.qml", modelData)
        }
    }

    // Visual panel & reservations
    Variants {
        model: Quickshell.screens

        Item {
            id: screenShellContainer
            required property ShellScreen modelData

            // Panel components (Bar, Notch, Dock, Frame, Corners)
            UnifiedShellPanel {
                id: unifiedPanel
                targetScreen: screenShellContainer.modelData
            }

            Loader {
                active: Config.theme.enableCorners && Config.roundness > 0
                sourceComponent: ScreenCorners {
                    screen: screenShellContainer.modelData
                }
            }

            // Exclusive zone reservations
            ReservationWindows {
                screen: screenShellContainer.modelData

                // Bar status for reservations
                barEnabled: {
                    const list = (Config.bar && Config.bar.screenList !== undefined ? Config.bar.screenList : []);
                    return (!list || list.length === 0 || list.indexOf(screen.name) !== -1);
                }
                barPosition: unifiedPanel.barPosition
                barPinned: unifiedPanel.pinned
                barSize: (unifiedPanel.barPosition === "left" || unifiedPanel.barPosition === "right") ? unifiedPanel.barTargetWidth : unifiedPanel.barTargetHeight
                barOuterMargin: unifiedPanel.barOuterMargin

                // Dock status for reservations
                dockEnabled: {
                    if (!((Config.dock && Config.dock.enabled !== undefined ? Config.dock.enabled : false)) || (Config.dock && Config.dock.theme !== undefined ? Config.dock.theme : "default") === "integrated")
                        return false;

                    const list = (Config.dock && Config.dock.screenList !== undefined ? Config.dock.screenList : []);
                    if (!list || list.length === 0)
                        return true;
                    return list.indexOf(screenShellContainer.modelData.name) !== -1;
                }
                dockPosition: unifiedPanel.dockPosition
                dockPinned: unifiedPanel.dockPinned
                dockHeight: unifiedPanel.dockHeight
                containBar: unifiedPanel.containBar

                frameEnabled: (Config.bar && Config.bar.frameEnabled !== undefined ? Config.bar.frameEnabled : false)
                frameThickness: (Config.bar && Config.bar.frameThickness !== undefined ? Config.bar.frameThickness : 6)
            }
        }
    }

    // Overview popup
    Variants {
        model: {
            const screens = Quickshell.screens;
            const list = (Config.bar && Config.bar.screenList !== undefined ? Config.bar.screenList : []);
            if (!list || list.length === 0)
                return screens;
            return screens.filter(screen => list.indexOf(screen.name) !== -1);
        }

        Loader {
            id: overviewLoader
            active: ((Config.overview && Config.overview.enabled !== undefined ? Config.overview.enabled : true)) && SuspendManager.wakeReady && Visibilities.currentActiveModule === "overview" && Visibilities.lastFocusedScreen === modelData.name
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadScreenItem(overviewLoader, "modules/widgets/overview/OverviewPopup.qml", modelData)
            Component.onCompleted: root._loadScreenItem(overviewLoader, "modules/widgets/overview/OverviewPopup.qml", modelData)
        }
    }

    // Assistant spotlight overlay
    Variants {
        model: {
            const screens = Quickshell.screens;
            const list = (Config.bar && Config.bar.screenList !== undefined ? Config.bar.screenList : []);
            if (!list || list.length === 0)
                return screens;
            return screens.filter(screen => list.indexOf(screen.name) !== -1);
        }

        Loader {
            id: assistantLoader
            active: SuspendManager.wakeReady && Visibilities.currentActiveModule === "assistant" && Visibilities.lastFocusedScreen === modelData.name
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadScreenItem(assistantLoader, "modules/widgets/assistant/AssistantPopup.qml", modelData)
            Component.onCompleted: root._loadScreenItem(assistantLoader, "modules/widgets/assistant/AssistantPopup.qml", modelData)
        }
    }

    Variants {
        model: Quickshell.screens

        Loader {
            id: computerUseHudLoader
            active: SuspendManager.wakeReady && ComputerUse.hudKeepAlive && ComputerUse.hudScreen === modelData.name
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadScreenItem(computerUseHudLoader, "modules/widgets/assistant/ComputerUseHud.qml", modelData)
            Component.onCompleted: root._loadScreenItem(computerUseHudLoader, "modules/widgets/assistant/ComputerUseHud.qml", modelData)
        }
    }

    // Secure WlSessionLock lockscreen
    WlSessionLock {
        id: sessionLock
        locked: GlobalStates.lockscreenVisible

        // Surface auto-created per screen
        LockScreen {}
    }

    CompositorConfig {
        id: compositorConfig
    }

    // Pushes Config.keybindsLoader (binds.json) keybinds into the compositor
    // live via `axctl config keybinds-batch` (runtime binds; not written to the
    // generated hyprland config).
    CompositorKeybinds {
        id: compositorKeybinds
    }

    // Screenshot tool
    Variants {
        model: Quickshell.screens

        Loader {
            id: screenshotLoader
            active: GlobalStates.screenshotToolVisible
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadNamedItem(screenshotLoader, "modules/tools/ScreenshotTool.qml", "targetScreen", modelData)
            Component.onCompleted: root._loadNamedItem(screenshotLoader, "modules/tools/ScreenshotTool.qml", "targetScreen", modelData)
        }
    }

    // Screenshot preview overlay
    Variants {
        model: Quickshell.screens

        Loader {
            id: screenshotOverlayLoader
            // Only exists while a preview is pending; the overlay re-reads
            // Screenshot.previewPath in its Component.onCompleted.
            active: SuspendManager.wakeReady && Screenshot.previewPath !== ""
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadNamedItem(screenshotOverlayLoader, "modules/tools/ScreenshotOverlay.qml", "targetScreen", modelData)
            Component.onCompleted: root._loadNamedItem(screenshotOverlayLoader, "modules/tools/ScreenshotOverlay.qml", "targetScreen", modelData)
        }
    }

    // Screen recording tool
    Loader {
        id: screenRecordLoader
        active: SuspendManager.wakeReady && GlobalStates.screenRecordToolVisible
        source: "modules/tools/ScreenrecordTool.qml"

        onLoaded: {
            if (GlobalStates.screenRecordToolVisible && item) {
                item.open();
            }
        }

        Connections {
            target: GlobalStates
            function onScreenRecordToolVisibleChanged() {
                if (screenRecordLoader.status === Loader.Ready) {
                    if (GlobalStates.screenRecordToolVisible) {
                        screenRecordLoader.item.open();
                    } else {
                        screenRecordLoader.item.close();
                    }
                }
            }
        }

        Connections {
            target: screenRecordLoader.item
            ignoreUnknownSignals: true
            function onVisibleChanged() {
                if (!screenRecordLoader.item.visible && GlobalStates.screenRecordToolVisible) {
                    GlobalStates.screenRecordToolVisible = false;
                }
            }
        }
    }

    // Mirror tool
    Loader {
        id: mirrorLoader
        active: SuspendManager.wakeReady && GlobalStates.mirrorWindowVisible
        source: "modules/tools/MirrorWindow.qml"
    }

    // Settings — defer creation until the notch has finished closing, so the
    // heavy new-window + SettingsTab instantiation can't stall the notch's
    // close animation on the main thread (which previously froze it ~1s).
    property bool settingsWindowDeferredActive: false

    Timer {
        id: settingsWindowDelayTimer
        interval: 425
        onTriggered: settingsWindowDeferredActive = GlobalStates.settingsWindowVisible
    }

    Connections {
        target: GlobalStates
        function onSettingsWindowVisibleChanged() {
            if (GlobalStates.settingsWindowVisible) {
                settingsWindowDelayTimer.restart();
            } else {
                settingsWindowDelayTimer.stop();
                settingsWindowDeferredActive = false;
            }
        }
    }

    Loader {
        id: settingsWindowLoader
        active: SuspendManager.wakeReady && settingsWindowDeferredActive
        source: "modules/widgets/config/SettingsWindow.qml"
    }

    // On-screen display — must stay loaded while awake. Audio/Brightness
    // Connections live inside OSD.qml and set GlobalStates.osdVisible; gating
    // the loader on osdVisible created a deadlock where volume/brightness
    // events never reached a listener after the first hide unloaded it.
    Variants {
        model: Quickshell.screens

        Loader {
            id: osdLoader
            active: SuspendManager.wakeReady
            required property ShellScreen modelData
            asynchronous: true
            onActiveChanged: root._loadNamedItem(osdLoader, "modules/shell/osd/OSD.qml", "targetScreen", modelData)
            Component.onCompleted: root._loadNamedItem(osdLoader, "modules/shell/osd/OSD.qml", "targetScreen", modelData)
        }
    }

    // Explicit service-init list. Referencing each singleton forces its load;
    // every service self-inits via its own Component.onCompleted / state-load
    // hook (FprintdInterceptor.update retries until Config is loaded).
    // Replaces the previous property-read hacks + 2s Timer.
    QtObject {
        id: serviceInitializer

        Component.onCompleted: {
            Qt.callLater(() => {
                // Critical services — init immediately (next tick)
                CaffeineService.toggleInhibit.toString();
                IdleService.executeCommand.toString();
                GlobalShortcuts.run.toString();
                // Non-critical services
                NightLightService.toggle.toString();
                GameModeService.toggle.toString();
                FprintdInterceptor.update.toString();
            });
        }
    }

    // Start fprintd monitoring when fingerprint auth is enabled
    Connections {
        target: Config.lockscreen
        function onEnableFingerprintChanged() {
            if (Config.lockscreen.enableFingerprint && FprintdInterceptor.active) {
                FprintdInterceptor.startMonitoring();
            } else {
                FprintdInterceptor.stopMonitoring();
            }
        }
    }
}
