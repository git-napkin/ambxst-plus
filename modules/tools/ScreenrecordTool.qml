import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.modules.theme
import qs.modules.components
import qs.modules.services
import qs.config

PanelWindow {
    id: screenrecordPopup

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

    visible: state !== "idle"
    exclusionMode: ExclusionMode.Ignore

    property string state: "idle" // idle, loading, active, processing
    property string currentMode: "region" // region, window, screen
    property var activeWindows: []

    property bool recordAudioOutput: false
    property bool recordAudioInput: false

    property var focusedMonitor: null // List of monitor objects from compositor

    function getModes() {
        return [
            {
                name: "audio",
                icon: recordAudioOutput ? Icons.speakerHigh : Icons.speakerSlash,
                tooltip: "Toggle Audio Output",
                type: "toggle",
                variant: recordAudioOutput ? "primary" : "focus"
            },
            {
                name: "mic",
                icon: recordAudioInput ? Icons.mic : Icons.micSlash,
                tooltip: "Toggle Microphone",
                type: "toggle",
                variant: recordAudioInput ? "primary" : "focus"
            },
            {
                type: "separator"
            },
            {
                name: "region",
                icon: Icons.regionScreenshot,
                tooltip: "Region"
            },
            {
                name: "window",
                icon: Icons.windowScreenshot,
                tooltip: "Window"
            },
            {
                name: "screen",
                icon: Icons.fullScreenshot,
                tooltip: "Screen"
            }
        ];
    }

    function open() {
        if (modeGrid)
            modeGrid.currentIndex = 3; // region
        screenrecordPopup.currentMode = "region";
        screenrecordPopup.recordAudioOutput = false;
        screenrecordPopup.recordAudioInput = false;
        
        // Fetch windows for window mode
        Screenshot.fetchWindows();
        
        // Go directly to active state (no freeze needed)
        screenrecordPopup.state = "active";
        
        // Force focus
        if (modeGrid)
            modeGrid.forceActiveFocus();
    }

    function close() {
        screenrecordPopup.state = "idle";
    }

    function targetMonitorName() {
        if (screenrecordPopup.focusedMonitor && screenrecordPopup.focusedMonitor.name)
            return screenrecordPopup.focusedMonitor.name;
        if (AxctlService.focusedMonitor && AxctlService.focusedMonitor.name)
            return AxctlService.focusedMonitor.name;
        return screenrecordPopup.screen ? screenrecordPopup.screen.name : "";
    }

    function monitorOrigin() {
        var mon = screenrecordPopup.focusedMonitor;
        if (mon && (mon.x !== undefined || mon.y !== undefined))
            return Qt.point(mon.x || 0, mon.y || 0);
        if (screenrecordPopup.screen)
            return Qt.point(screenrecordPopup.screen.x, screenrecordPopup.screen.y);
        return Qt.point(0, 0);
    }

    function startCapture(mode, regionStr) {
        ScreenRecorder.startRecording(screenrecordPopup.recordAudioOutput, screenrecordPopup.recordAudioInput, mode, regionStr || "", screenrecordPopup.targetMonitorName());
        screenrecordPopup.close();
    }

    function executeCapture() {
        if (screenrecordPopup.currentMode === "screen") {
            screenrecordPopup.startCapture("screen", "");
        } else if (screenrecordPopup.currentMode === "region") {
            if (selectionRect.width > 0) {
                var w = Math.round(selectionRect.width);
                var h = Math.round(selectionRect.height);
                var origin = screenrecordPopup.monitorOrigin();
                var x = Math.round(selectionRect.x) + origin.x;
                var y = Math.round(selectionRect.y) + origin.y;
                screenrecordPopup.startCapture("region", w + "x" + h + "+" + x + "+" + y);
            }
        }
    }

    Connections {
        target: Screenshot
        function onMonitorsListReady(monitors) {
            screenrecordPopup.focusedMonitor = monitors.find(m => m.focused);
        }
        function onWindowListReady(windows) {
            screenrecordPopup.activeWindows = windows;
        }
    }

    mask: Region {
        item: screenrecordPopup.visible ? fullMask : emptyMask
    }

    Item {
        id: fullMask
        anchors.fill: parent
    }

    Item {
        id: emptyMask
        width: 0
        height: 0
    }

    FocusGrab {
        id: focusGrab
        windows: [screenrecordPopup]
        active: screenrecordPopup.visible
    }

    FocusScope {
        id: mainFocusScope
        anchors.fill: parent
        focus: true

        Keys.onEscapePressed: screenrecordPopup.close()

        // Dimmer overlay (semi-transparent)
        Rectangle {
            anchors.fill: parent
            color: "black"
            opacity: screenrecordPopup.state === "active" ? 0.4 : 0
            visible: screenrecordPopup.state === "active" && screenrecordPopup.currentMode !== "screen"
        }

        Item {
            anchors.fill: parent
            visible: screenrecordPopup.state === "active" && screenrecordPopup.currentMode === "window"

            Repeater {
                model: screenrecordPopup.activeWindows
                delegate: Rectangle {
                    x: modelData.at[0] - screenrecordPopup.screen.x
                    y: modelData.at[1] - screenrecordPopup.screen.y
                    width: modelData.size[0]
                    height: modelData.size[1]
                    color: "transparent"
                    border.color: hoverHandler.hovered ? Styling.srItem("overprimary") : "transparent"
                    border.width: 2

                    Rectangle {
                        anchors.fill: parent
                        color: Styling.srItem("overprimary")
                        opacity: hoverHandler.hovered ? Styling.hoverAlpha : 0
                    }

                    HoverHandler {
                        id: hoverHandler
                    }

                    TapHandler {
                        onTapped: {
                            var w = Math.round(modelData.size[0]);
                            var h = Math.round(modelData.size[1]);
                            var x = Math.round(modelData.at[0]);
                            var y = Math.round(modelData.at[1]);

                            screenrecordPopup.startCapture("region", w + "x" + h + "+" + x + "+" + y);
                        }
                    }
                }
            }
        }

        MouseArea {
            id: regionArea
            anchors.fill: parent
            enabled: screenrecordPopup.state === "active" && (screenrecordPopup.currentMode === "region" || screenrecordPopup.currentMode === "screen")
            hoverEnabled: true
            cursorShape: screenrecordPopup.currentMode === "region" ? Qt.CrossCursor : Qt.ArrowCursor

            property point startPoint: Qt.point(0, 0)
            property bool selecting: false

            onPressed: mouse => {
                if (screenrecordPopup.currentMode === "screen") {
                    return;
                }

                startPoint = Qt.point(mouse.x, mouse.y);
                selectionRect.x = mouse.x;
                selectionRect.y = mouse.y;
                selectionRect.width = 0;
                selectionRect.height = 0;
                selecting = true;
            }

            onClicked: {
                if (screenrecordPopup.currentMode === "screen") {
                    screenrecordPopup.startCapture("screen", "");
                }
            }

            onPositionChanged: mouse => {
                if (!selecting)
                    return;
                var x = Math.min(startPoint.x, mouse.x);
                var y = Math.min(startPoint.y, mouse.y);
                var w = Math.abs(startPoint.x - mouse.x);
                var h = Math.abs(startPoint.y - mouse.y);

                selectionRect.x = x;
                selectionRect.y = y;
                selectionRect.width = w;
                selectionRect.height = h;
            }

            onReleased: {
                if (!selecting)
                    return;
                selecting = false;
                if (selectionRect.width > 5 && selectionRect.height > 5) {
                    var w = Math.round(selectionRect.width);
                    var h = Math.round(selectionRect.height);
                    var origin = screenrecordPopup.monitorOrigin();
                    var x = Math.round(selectionRect.x) + origin.x;
                    var y = Math.round(selectionRect.y) + origin.y;
                    screenrecordPopup.startCapture("region", w + "x" + h + "+" + x + "+" + y);
                }
            }
        }

        Rectangle {
            id: selectionRect
            visible: screenrecordPopup.state === "active" && screenrecordPopup.currentMode === "region"
            color: "transparent"
            border.color: Styling.srItem("overprimary")
            border.width: 2

            Rectangle {
                anchors.fill: parent
                color: Styling.srItem("overprimary")
                opacity: 0.2
            }
        }

        Rectangle {
            id: controlsBar
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: 50

            width: modeGrid.width + 32
            height: modeGrid.height + 32

            radius: Styling.radius(20)
            color: Colors.background
            border.color: Colors.surface
            border.width: 1
            visible: screenrecordPopup.state === "active"

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                preventStealing: true
            }

            ActionGrid {
                id: modeGrid
                anchors.centerIn: parent
                actions: screenrecordPopup.getModes()
                buttonSize: 48
                iconSize: 24
                spacing: 10

                onCurrentIndexChanged: {
                    // Skip toggles and separator
                    if (currentIndex > 2) {
                        var captureIndex = currentIndex - 3;
                        var captureOptions = ["region", "window", "screen"];
                        if (captureIndex >= 0 && captureIndex < captureOptions.length) {
                            screenrecordPopup.currentMode = captureOptions[captureIndex];
                        }
                    }
                }

                onActionTriggered: action => {
                    if (action.tooltip === "Toggle Audio Output") {
                        screenrecordPopup.recordAudioOutput = !screenrecordPopup.recordAudioOutput;
                    } else if (action.tooltip === "Toggle Microphone") {
                        screenrecordPopup.recordAudioInput = !screenrecordPopup.recordAudioInput;
                    } else {
                        screenrecordPopup.executeCapture();
                    }
                }
            }
        }
    }
}
