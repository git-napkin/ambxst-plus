import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland
import qs.modules.globals
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.modules.sidebar
import qs.config
import "."

PanelWindow {
    id: assistantPopup

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "ambxst+:assistant"
    WlrLayershell.keyboardFocus: assistantOpen && !ComputerUse.sessionActive ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Keys.enabled: assistantOpen && !ComputerUse.sessionActive
    Keys.priority: Keys.BeforeItem
    Keys.onPressed: event => {
        if (AxctlService.forwardBoundKey(event))
            event.accepted = true;
    }

    readonly property var screenVisibilities: Visibilities.getForScreen(screen.name)
    readonly property bool assistantOpen: screenVisibilities ? screenVisibilities.assistant : false

    readonly property int overlayWidth: Math.min(Config.ai.overlayWidth || 640, width - 48)
    readonly property real overlayY: height * (Config.ai.overlayYFraction ?? 0.22)
    readonly property int barHeight: bar.implicitHeight
    readonly property int maxBodyHeight: Math.round(height * 0.6) - 56

    visible: assistantOpen && !ComputerUse.sessionActive
    exclusionMode: ExclusionMode.Ignore
    property bool restoringAfterComputerUse: false

    mask: Region {
        item: assistantOpen && !ComputerUse.sessionActive ? fullMask : emptyMask
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
        windows: [assistantPopup]
        active: assistantOpen && !ComputerUse.sessionActive && !assistantPopup.restoringAfterComputerUse

        onCleared: {
            if (assistantPopup.restoringAfterComputerUse)
                return;
            Qt.callLater(() => {
                if (assistantOpen)
                    Visibilities.setActiveModule("");
            });
        }
    }

    Rectangle {
        id: backdrop
        anchors.fill: parent
        color: Colors.scrim
        opacity: assistantOpen && !ComputerUse.sessionActive && (Config.ai.showScrim ?? true) ? 0.5 : 0

        Behavior on opacity {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Config.animDuration
                easing.type: Styling.animEasingOut
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: Visibilities.setActiveModule("")
        }
    }

    Item {
        id: mainContainer
        width: assistantPopup.overlayWidth
        height: bar.height + body.height + ((idleList.visible || transcript.visible) ? 8 : 0)
        x: Math.round((assistantPopup.width - width) / 2)
        y: Math.round(assistantPopup.overlayY)

        opacity: assistantOpen && !ComputerUse.sessionActive ? 1 : 0
        scale: assistantOpen && !ComputerUse.sessionActive ? 1 : 0.96
        transformOrigin: Item.Top

        Behavior on opacity {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Config.animDuration
                easing.type: Styling.animEasingOut
            }
        }

        Behavior on scale {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Config.animDuration
                easing.type: Styling.animEasingOut
            }
        }

        AssistantBar {
            id: bar
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            implicitHeight: 52
            idleOpen: idleList.visible
            idleSelected: idleList.selectedIndex
            onOpenModelSelector: modelSelector.open()
            onRequestClose: Visibilities.setActiveModule("")
            onIdleActivate: idleList.activateSelected()
            onIdleMove: delta => idleList.moveSelection(delta)
        }

        Item {
            id: body
            anchors.top: bar.bottom
            anchors.topMargin: (idleList.visible || transcript.visible) ? 8 : 0
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            height: idleList.visible ? idleList.implicitHeight : (transcript.visible ? transcript.height : 0)

            AssistantIdleList {
                id: idleList
                anchors.top: parent.top
                width: parent.width
                visible: Ai.currentChat.length === 0 && !Ai.isLoading && implicitHeight > 0
                filterText: bar.inputText
                onActivated: item => bar.activateIdle(item)
            }

            AssistantTranscript {
                id: transcript
                anchors.top: parent.top
                width: parent.width
                height: Math.min(contentHeight, assistantPopup.maxBodyHeight)
                visible: Ai.currentChat.length > 0 || Ai.isLoading
            }
        }
    }

    ModelSelectorPopup {
        id: modelSelector
        parent: mainContainer
        onModelSelected: name => Ai.setModel(name)
    }

    Connections {
        target: Ai
        function onModelSelectionRequested() {
            modelSelector.open();
        }
    }

    onAssistantOpenChanged: {
        if (assistantOpen && !ComputerUse.sessionActive) {
            Qt.callLater(() => bar.focusInput());
        }
    }

    Connections {
        target: ComputerUse
        function onSessionActiveChanged() {
            if (assistantOpen && !ComputerUse.sessionActive) {
                assistantPopup.restoringAfterComputerUse = true;
                restoreGrabTimer.restart();
                Qt.callLater(() => bar.focusInput());
            }
        }
    }

    Timer {
        id: restoreGrabTimer
        interval: 120
        repeat: false
        onTriggered: assistantPopup.restoringAfterComputerUse = false
    }

    Component.onCompleted: {
        if (assistantOpen && !ComputerUse.sessionActive)
            bar.focusInput();
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: assistantOpen && !ComputerUse.sessionActive
        onActivated: Ai.createNewChat()
    }

    Shortcut {
        sequence: "Ctrl+R"
        enabled: assistantOpen && !ComputerUse.sessionActive
        onActivated: Ai.regenerateLast()
    }
}
