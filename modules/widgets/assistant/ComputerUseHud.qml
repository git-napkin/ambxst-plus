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
        if (ComputerUse.sessionState === "approvalWait" || (hud.cardVisible && ComputerUse.composerFocused))
            return WlrKeyboardFocus.Exclusive;
        return WlrKeyboardFocus.None;
    }

    mask: Region {
        item: hud.clickThrough ? emptyMask : hudRoot
    }

    Item {
        id: emptyMask
        width: 0
        height: 0
    }

    readonly property int minWidth: 280
    readonly property int maxWidth: 420
    readonly property int pad: 10
    readonly property int screenH: screen ? screen.height : 900
    readonly property int bodyMax: Math.round(screenH * 0.4)
    readonly property int innerRadius: Math.max(0, Styling.popupRadius() - pad)
    property bool cardVisible: false
    readonly property bool showChip: ComputerUse.sessionActive && ComputerUse.userHasControl
    readonly property bool clickThrough: !hud.cardVisible && !hud.showChip
    readonly property string assistantText: {
        const chat = Ai.currentChat || [];
        for (let i = chat.length - 1; i >= 0; i--) {
            const msg = chat[i];
            if (msg.role === "assistant") {
                const text = String(msg.content || "").trim();
                if (text.length)
                    return String(msg.content || "");
            }
        }
        return "";
    }
    readonly property string steerText: {
        const chat = Ai.currentChat || [];
        for (let i = chat.length - 1; i >= 0; i--) {
            const msg = chat[i];
            if (msg.role === "user")
                return String(msg.content || "").trim();
            if (msg.role === "assistant" && String(msg.content || "").trim().length)
                break;
        }
        return "";
    }
    readonly property bool streaming: !!(Ai.isLoading && assistantText.length)

    onAssistantTextChanged: hud.refreshPresence()
    onStreamingChanged: hud.refreshPresence()

    onCardVisibleChanged: {
        if (!hud.cardVisible)
            ComputerUse.composerFocused = false;
    }

    function refreshPresence() {
        if (!ComputerUse.sessionActive || ComputerUse.hudHiddenForCapture) {
            hud.cardVisible = false;
            return;
        }
        if (Ai.approvalPending || ComputerUse.composerFocused) {
            ComputerUse.hudCollapsed = false;
            hud.cardVisible = true;
            hideTimer.stop();
            return;
        }
        if (ComputerUse.userHasControl || ComputerUse.hudCollapsed) {
            hud.cardVisible = false;
            hideTimer.stop();
            return;
        }
        if (!hud.assistantText.length) {
            hud.cardVisible = false;
            return;
        }
        hud.cardVisible = true;
        if (hud.streaming) {
            hideTimer.stop();
            return;
        }
        hideTimer.restart();
    }

    FocusGrab {
        id: focusGrab
        windows: [hud]
        active: ComputerUse.sessionState === "approvalWait"
    }

    Timer {
        id: hideTimer
        interval: 3000
        repeat: false
        onTriggered: {
            if (Ai.approvalPending || ComputerUse.composerFocused)
                return;
            hud.cardVisible = false;
        }
    }

    Connections {
        target: Ai
        function onLastHudActivityAtChanged() {
            ComputerUse.hudCollapsed = false;
            hud.refreshPresence();
        }
        function onApprovalPendingChanged() {
            hud.refreshPresence();
        }
        function onChatModelChanged() {
            hud.refreshPresence();
        }
        function onIsLoadingChanged() {
            hud.refreshPresence();
        }
    }

    Connections {
        target: ComputerUse
        function onSessionActiveChanged() {
            hud.refreshPresence();
        }
        function onUserHasControlChanged() {
            hud.refreshPresence();
        }
        function onComposerFocusedChanged() {
            hud.refreshPresence();
        }
        function onHudCollapsedChanged() {
            hud.refreshPresence();
        }
    }

    Item {
        id: hudRoot
        width: Math.round(Math.min(hud.maxWidth, Math.max(hud.minWidth, ComputerUse.hudWidth)))
        height: {
            if (hud.showChip && !hud.cardVisible)
                return chip.height;
            if (!hud.cardVisible)
                return 1;
            return card.height;
        }
        opacity: (hud.cardVisible || hud.showChip) ? 1 : 0
        y: (hud.cardVisible || hud.showChip) ? 0 : 12

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

        Item {
            id: chip
            visible: hud.showChip && !hud.cardVisible
            width: parent.width
            height: visible ? 44 : 0

            StyledRect {
                anchors.fill: parent
                variant: "popup"
                radius: Styling.popupRadius()
                layer.enabled: true
                layer.effect: Shadow {}
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: hud.pad
                anchors.rightMargin: 4
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: qsTr("You have control")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    font.weight: Font.Medium
                    color: Colors.overSurface
                    elide: Text.ElideRight
                }

                HudIconButton {
                    icon: Icons.handGrab
                    tooltip: qsTr("Hand back")
                    onClicked: ComputerUse.handBack()
                }

                HudIconButton {
                    icon: Icons.stop
                    tooltip: qsTr("Stop")
                    onClicked: Ai.stopComputerUse()
                }
            }
        }

        Item {
            id: card
            visible: hud.cardVisible
            width: parent.width
            height: visible ? (header.height + body.height + 8 + footer.height + (composer.visible ? composer.height + 8 : 0) + hud.pad) : 0

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
                anchors.topMargin: 6
                height: hud.steerText.length && !Ai.approvalPending ? 28 : 0

                Rectangle {
                    visible: header.height > 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: hud.pad
                    anchors.rightMargin: hud.pad
                    height: 22
                    radius: Math.max(0, hud.innerRadius - 6)
                    color: Styling.tint(Colors.primary, 0.18)

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        text: hud.steerText
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-3)
                        color: Colors.primary
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            Item {
                id: body
                anchors.top: header.bottom
                anchors.topMargin: header.height > 0 ? 4 : 0
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: hud.pad
                anchors.rightMargin: hud.pad
                height: {
                    if (Ai.approvalPending)
                        return Math.min(approvalLoader.implicitHeight, hud.bodyMax);
                    return Math.min(markdown.implicitHeight, hud.bodyMax);
                }
                clip: true

                ApprovalCard {
                    id: approvalLoader
                    visible: Ai.approvalPending
                    width: parent.width
                    call: Ai.pendingApproval || ({})
                }

                AssistantMessage {
                    id: markdown
                    visible: !Ai.approvalPending
                    width: parent.width
                    message: ({
                            role: "assistant",
                            content: hud.assistantText
                        })
                }

                Rectangle {
                    visible: !Ai.approvalPending && markdown.implicitHeight > body.height
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 28
                    gradient: Gradient {
                        GradientStop {
                            position: 0
                            color: Qt.rgba(Colors.background.r, Colors.background.g, Colors.background.b, 0)
                        }
                        GradientStop {
                            position: 1
                            color: Styling.tint(Colors.background, 0.92)
                        }
                    }
                }
            }

            Item {
                id: footer
                anchors.top: body.bottom
                anchors.topMargin: 8
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                height: 40

                RowLayout {
                    anchors.fill: parent
                    spacing: 2

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

                    Item { Layout.fillWidth: true }

                    Text {
                        visible: hud.streaming
                        text: qsTr("Waiting")
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-4)
                        color: Colors.outline
                    }

                    HudIconButton {
                        icon: Icons.minusCircle
                        tooltip: qsTr("Hide")
                        onClicked: {
                            ComputerUse.hudCollapsed = true;
                            hud.cardVisible = false;
                        }
                    }
                }
            }

            Item {
                id: composer
                visible: !ComputerUse.userHasControl && hud.cardVisible
                anchors.top: footer.bottom
                anchors.topMargin: 8
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: hud.pad
                anchors.rightMargin: hud.pad
                height: 44

                StyledRect {
                    anchors.fill: parent
                    variant: "internalbg"
                    radius: hud.innerRadius
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
                    when: hud.visible && hud.cardVisible
                }
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

    component HudIconButton: Item {
        id: btn
        property string icon: ""
        property string tooltip: ""
        signal clicked
        implicitWidth: 40
        implicitHeight: 40
        scale: area.pressed ? 0.96 : 1

        StyledRect {
            anchors.centerIn: parent
            width: 28
            height: 28
            variant: "internalbg"
            radius: Styling.radius(-4)

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
