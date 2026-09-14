import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
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
    WlrLayershell.keyboardFocus: assistantOpen ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    readonly property var screenVisibilities: Visibilities.getForScreen(screen.name)
    readonly property bool assistantOpen: screenVisibilities ? screenVisibilities.assistant : false

    readonly property int overlayWidth: Math.min(Config.ai.overlayWidth || 640, width - 48)
    readonly property real overlayY: height * (Config.ai.overlayYFraction ?? 0.22)
    readonly property int barHeight: bar.implicitHeight
    readonly property int maxBodyHeight: Math.round(height * 0.6) - 56

    visible: assistantOpen
    exclusionMode: ExclusionMode.Ignore

    mask: Region {
        item: assistantOpen ? fullMask : emptyMask
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
        active: assistantOpen

        onCleared: {
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
        opacity: assistantOpen && (Config.ai.showScrim ?? true) ? 0.5 : 0

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
        height: bar.height + (footer.visible ? footer.height + 8 : 0) + body.height + ((idleList.visible || transcript.visible) ? 8 : 0)
        x: Math.round((assistantPopup.width - width) / 2)
        y: Math.round(assistantPopup.overlayY)

        opacity: assistantOpen ? 1 : 0
        scale: assistantOpen ? 1 : 0.96
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
            implicitHeight: 56
            onOpenModelSelector: modelSelector.open()
            onRequestClose: Visibilities.setActiveModule("")
        }

        RowLayout {
            id: footer
            anchors.top: bar.bottom
            anchors.topMargin: 8
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 8
            visible: Ai.currentChat.length > 0 || Ai.isLoading
            height: visible ? 24 : 0

            StyledRect {
                variant: "surface"
                radius: Styling.radius(-4)
                implicitHeight: 24
                implicitWidth: modelLabel.implicitWidth + 16
                scale: modelArea.pressed ? 0.96 : 1

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: modelArea.containsMouse ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
                }

                Text {
                    id: modelLabel
                    anchors.centerIn: parent
                    text: Ai.currentModel ? Ai.currentModel.name : qsTr("Select model")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-3)
                    color: Colors.overSurface
                }

                MouseArea {
                    id: modelArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: modelSelector.open()
                }
            }

            StyledRect {
                variant: Ai.autoApprove ? "primary" : "surface"
                radius: Styling.radius(-4)
                implicitHeight: 24
                implicitWidth: autoLabel.implicitWidth + 16
                scale: autoArea.pressed ? 0.96 : 1

                Text {
                    id: autoLabel
                    anchors.centerIn: parent
                    text: Ai.autoApprove ? qsTr("Allow this chat") : qsTr("Ask to run")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-3)
                    color: Ai.autoApprove ? Colors.overPrimary : Colors.overSurface
                }

                MouseArea {
                    id: autoArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Ai.setAutoApprove(!Ai.autoApprove)
                }
            }
        }

        Item {
            id: body
            anchors.top: footer.visible ? footer.bottom : bar.bottom
            anchors.topMargin: (idleList.visible || transcript.visible) ? 8 : 0
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            height: idleList.visible ? idleList.implicitHeight : (transcript.visible ? transcript.height : 0)

            AssistantIdleList {
                id: idleList
                anchors.top: parent.top
                width: parent.width
                visible: Ai.currentChat.length === 0 && !Ai.isLoading
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
        parent: assistantPopup.contentItem
        onModelSelected: name => Ai.setModel(name)
    }

    Connections {
        target: Ai
        function onModelSelectionRequested() {
            modelSelector.open();
        }
    }

    onAssistantOpenChanged: {
        if (assistantOpen) {
            Qt.callLater(() => bar.focusInput());
        }
    }

    Component.onCompleted: {
        if (assistantOpen)
            bar.focusInput();
    }

    Shortcut {
        sequence: "Ctrl+N"
        enabled: assistantOpen
        onActivated: Ai.createNewChat()
    }

    Shortcut {
        sequence: "Ctrl+R"
        enabled: assistantOpen
        onActivated: Ai.regenerateLast()
    }
}
