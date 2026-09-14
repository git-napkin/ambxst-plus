import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.modules.globals
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config
import "."

PanelWindow {
    id: hud

    implicitWidth: hudRoot.width
    implicitHeight: hudRoot.height
    color: "transparent"
    visible: ComputerUse.sessionActive && !ComputerUse.hudHiddenForCapture
    exclusionMode: ExclusionMode.Ignore

    anchors {
        right: true
        bottom: true
    }
    margins {
        right: ComputerUse.insetRight
        bottom: ComputerUse.insetBottom
    }

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "ambxst+:computer-use"
    WlrLayershell.keyboardFocus: {
        if (!ComputerUse.sessionActive)
            return WlrKeyboardFocus.None;
        if (ComputerUse.sessionState === "approvalWait" || ComputerUse.composerFocused)
            return WlrKeyboardFocus.Exclusive;
        return WlrKeyboardFocus.None;
    }

    mask: Region {
        item: hud.visible ? hudRoot : emptyMask
    }

    Item {
        id: emptyMask
        width: 0
        height: 0
    }

    readonly property int minWidth: 280
    readonly property int maxWidth: 480
    readonly property int headerHeight: 40
    readonly property int composerHeight: ComputerUse.userHasControl || ComputerUse.hudCollapsed ? 0 : 52
    readonly property int screenH: screen ? screen.height : 900
    readonly property int maxHudHeight: Math.round(screenH * 0.5)
    readonly property int bodyMax: {
        if (ComputerUse.hudCollapsed)
            return 0;
        if (Ai.approvalPending)
            return Math.max(120, maxHudHeight - headerHeight - composerHeight - 16);
        return 280;
    }

    FocusGrab {
        id: focusGrab
        windows: [hud]
        active: ComputerUse.sessionState === "approvalWait"
    }

    Item {
        id: hudRoot
        width: Math.round(Math.min(hud.maxWidth, Math.max(hud.minWidth, ComputerUse.hudWidth)))
        height: header.height + (body.visible ? body.height + 8 : 0) + (composer.visible ? composer.height + 8 : 0)
        opacity: ComputerUse.sessionActive ? 1 : 0
        y: ComputerUse.sessionActive ? 0 : 18

        Behavior on opacity {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Config.animDuration
                easing.type: Styling.animEasing
            }
        }
        Behavior on y {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Config.animDuration
                easing.type: Styling.animEasing
            }
        }

        StyledRect {
            anchors.fill: parent
            variant: "popup"
            radius: Styling.popupRadius()
            layer.enabled: true
            layer.effect: Shadow {}
        }

        MouseArea {
            id: resizeEdge
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 8
            cursorShape: Qt.SizeHorCursor
            property real startW: 360
            onPressed: startW = ComputerUse.hudWidth
            onPositionChanged: ComputerUse.hudWidth = Math.min(hud.maxWidth, Math.max(hud.minWidth, startW - mouseX))
        }

        Item {
            id: header
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: hud.headerHeight

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 6
                spacing: 6

                Text {
                    text: Icons.mouse
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.primary
                }

                Column {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        width: parent.width
                        text: ComputerUse.userHasControl ? qsTr("You have control") : qsTr("Using computer")
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        font.weight: Font.Medium
                        color: Colors.overSurface
                        elide: Text.ElideRight
                    }
                    Text {
                        width: parent.width
                        visible: (ComputerUse.lastAction || "").length > 0
                        text: ComputerUse.lastAction
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-4)
                        color: Colors.outline
                        elide: Text.ElideRight
                    }
                }

                HudIconButton {
                    icon: ComputerUse.userHasControl ? Icons.handGrab : Icons.hand
                    tooltip: ComputerUse.userHasControl ? qsTr("Hand back") : qsTr("Take control")
                    onClicked: ComputerUse.userHasControl ? ComputerUse.handBack() : ComputerUse.takeControl()
                }

                HudIconButton {
                    icon: Icons.stop
                    tooltip: qsTr("Stop")
                    onClicked: Ai.stopComputerUse()
                }

                HudIconButton {
                    icon: ComputerUse.hudCollapsed ? Icons.caretUp : Icons.caretDown
                    tooltip: ComputerUse.hudCollapsed ? qsTr("Expand") : qsTr("Collapse")
                    onClicked: ComputerUse.hudCollapsed = !ComputerUse.hudCollapsed
                }
            }
        }

        Item {
            id: body
            visible: !ComputerUse.hudCollapsed
            anchors.top: header.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            height: Math.min(transcript.contentHeight, hud.bodyMax)
            clip: true

            AssistantTranscript {
                id: transcript
                anchors.fill: parent
                compact: true
            }
        }

        Item {
            id: composer
            visible: !ComputerUse.userHasControl && !ComputerUse.hudCollapsed
            anchors.top: body.visible ? body.bottom : header.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            height: hud.composerHeight

            StyledRect {
                anchors.fill: parent
                variant: "internalbg"
                radius: Math.max(0, Styling.popupRadius() - 8)
            }

            SearchInput {
                id: steerInput
                anchors.fill: parent
                variant: "transparent"
                placeholderText: qsTr("Steer the agent…")
                clearOnEscape: false
                onAccepted: {
                    const text = steerInput.text.trim();
                    if (Ai.isLoading) {
                        Ai.cancel();
                        return;
                    }
                    if (!text.length)
                        return;
                    Ai.sendMessage(text);
                    steerInput.clear();
                }
                onEscapePressed: {
                    if (Ai.approvalPending)
                        Ai.rejectPendingApproval();
                    else
                        steerInput.blurInput();
                }
            }

            Binding {
                target: ComputerUse
                property: "composerFocused"
                value: steerInput.inputActive
                when: hud.visible
            }
        }
    }

    Shortcut {
        sequence: "Return"
        enabled: ComputerUse.sessionState === "approvalWait"
        onActivated: Ai.approvePendingApproval()
    }
    Shortcut {
        sequence: "Enter"
        enabled: ComputerUse.sessionState === "approvalWait"
        onActivated: Ai.approvePendingApproval()
    }
    Shortcut {
        sequence: "Escape"
        enabled: ComputerUse.sessionState === "approvalWait"
        onActivated: Ai.rejectPendingApproval()
    }

    component HudIconButton: StyledRect {
        id: btn
        property string icon: ""
        property string tooltip: ""
        signal clicked
        variant: "internalbg"
        radius: Styling.radius(-4)
        implicitWidth: 28
        implicitHeight: 28
        scale: area.pressed ? 0.96 : 1

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: area.containsMouse ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
        }

        Text {
            anchors.centerIn: parent
            text: btn.icon
            font.family: Icons.font
            font.pixelSize: Styling.fontSize(-2)
            color: Colors.overSurface
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
        Behavior on scale {
            enabled: Config.animDuration > 0
            NumberAnimation {
                duration: Styling.animQuick
                easing.type: Styling.animEasingOut
            }
        }
    }
}
