import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.modules.globals
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config
import qs.modules.widgets.assistant

PanelWindow {
    id: hud

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }
    color: "transparent"
    visible: ComputerUse.sessionActive
    exclusionMode: ExclusionMode.Ignore

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "ambxst+:computer-use"
    WlrLayershell.keyboardFocus: {
        if (!ComputerUse.sessionActive)
            return WlrKeyboardFocus.None;
        if (ComputerUse.userHasControl || ComputerUse.injectingInput)
            return WlrKeyboardFocus.None;
        return WlrKeyboardFocus.Exclusive;
    }

    mask: Region {
        item: ComputerUse.sessionState === "approvalWait" ? inputBlock : (hud.clickThrough ? grabPixel : hudAnchor)
    }

    Item {
        id: grabPixel
        width: 1
        height: 1
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }

    Item {
        id: inputBlock
        anchors.fill: parent
        z: 0
        visible: ComputerUse.sessionState === "approvalWait"

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onPressed: mouse => {
                mouse.accepted = true;
            }
        }
    }

    readonly property int minWidth: 280
    readonly property int maxWidth: 420
    readonly property int pad: 10
    readonly property int screenH: screen ? screen.height : 900
    readonly property int bodyMax: Math.round(screenH * 0.4)
    readonly property int innerRadius: Math.max(0, Styling.popupRadius() - pad)
    property bool cardVisible: false
    readonly property bool showChip: ComputerUse.sessionActive && ComputerUse.userHasControl
    readonly property bool clickThrough: !hud.cardVisible && !hud.showChip && !ComputerUse.steerOpen
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

    function claimKeys() {
        if (!ComputerUse.sessionActive || ComputerUse.userHasControl || ComputerUse.injectingInput)
            return;
        if (hud.requestActivate)
            hud.requestActivate();
        hudAnchor.forceActiveFocus();
        if (ComputerUse.steerOpen)
            Qt.callLater(() => steerInput.focusInput());
    }

    function openSteer(ch) {
        ComputerUse.steerOpen = true;
        ComputerUse.hudCollapsed = false;
        if (ch)
            steerInput.text = String(steerInput.text || "") + ch;
        Qt.callLater(() => steerInput.focusInput());
    }

    function closeSteer() {
        ComputerUse.steerOpen = false;
        ComputerUse.composerFocused = false;
        steerInput.blurInput();
        steerInput.clear();
        hud.claimKeys();
    }

    function handleUserKey(event) {
        if (ComputerUse.steerOpen || ComputerUse.userHasControl || ComputerUse.injectingInput)
            return;
        if (Ai.approvalPending)
            return;
        if (event.modifiers & Qt.ControlModifier || event.modifiers & Qt.AltModifier || event.modifiers & Qt.MetaModifier)
            return;
        if (event.key === Qt.Key_Escape || event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Tab)
            return;
        if (event.key === Qt.Key_Backspace) {
            hud.openSteer("");
            event.accepted = true;
            return;
        }
        const ch = event.text || "";
        if (ch.length && ch.charCodeAt(0) >= 32) {
            hud.openSteer(ch);
            event.accepted = true;
        }
    }

    function submitSteer() {
        const text = String(steerInput.text || "").trim();
        if (!text.length)
            return;
        if (Ai.isLoading)
            Ai.cancel();
        Ai.sendMessage(text);
        hud.closeSteer();
    }

    function refreshPresence() {
        if (!ComputerUse.sessionActive || ComputerUse.hudHiddenForCapture) {
            hud.cardVisible = false;
            return;
        }
        if (Ai.approvalPending) {
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
            if (Ai.approvalPending)
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
            if (Ai.approvalPending)
                hud.claimKeys();
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
            if (!ComputerUse.sessionActive)
                hud.closeSteer();
            else
                hud.claimKeys();
            hud.refreshPresence();
        }
        function onUserHasControlChanged() {
            if (ComputerUse.userHasControl)
                hud.closeSteer();
            else
                hud.claimKeys();
            hud.refreshPresence();
        }
        function onHudCollapsedChanged() {
            hud.refreshPresence();
        }
        function onInjectingInputChanged() {
            if (!ComputerUse.injectingInput)
                hud.claimKeys();
        }
        function onSteerOpenChanged() {
            ComputerUse.composerFocused = ComputerUse.steerOpen;
            if (!ComputerUse.steerOpen) {
                steerInput.blurInput();
                steerInput.clear();
                hud.claimKeys();
            }
        }
    }

    Binding {
        target: ComputerUse
        property: "composerFocused"
        value: ComputerUse.steerOpen
        when: ComputerUse.sessionActive
    }

    Component.onCompleted: hud.claimKeys()
    onVisibleChanged: if (visible)
        hud.claimKeys()

    Item {
        id: hudAnchor
        focus: ComputerUse.sessionActive && !ComputerUse.userHasControl && !ComputerUse.injectingInput
        // PanelWindow is not an Item — Keys must live on a child Item.
        Keys.enabled: ComputerUse.sessionActive && !ComputerUse.userHasControl && !ComputerUse.injectingInput
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: event => {
            if (ComputerUse.sessionState === "approvalWait") {
                if (event.key === Qt.Key_Left) {
                    approvalLoader.focusedAction = "reject";
                    event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_Right) {
                    approvalLoader.focusedAction = "approve";
                    event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    approvalLoader.confirmFocused();
                    event.accepted = true;
                    return;
                }
            }
            if (AxctlService.forwardBoundKey(event)) {
                event.accepted = true;
                return;
            }
            if (event.key === Qt.Key_Escape) {
                ComputerUse.handleEscape();
                event.accepted = true;
                return;
            }
            hud.handleUserKey(event);
        }
        z: 1
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: ComputerUse.insetRight
        anchors.bottomMargin: ComputerUse.insetBottom
        width: hudRoot.width
        height: hudRoot.height

        Item {
            id: hudRoot
            width: Math.round(Math.min(hud.maxWidth, Math.max(hud.minWidth, ComputerUse.hudWidth)))
            height: {
                let h = 0;
                if (hud.showChip && !hud.cardVisible)
                    h += chip.height;
                if (hud.cardVisible)
                    h += card.height;
                if (ComputerUse.steerOpen && !ComputerUse.userHasControl)
                    h += (h > 0 ? 8 : 0) + steerBox.height;
                return Math.max(h, 1);
            }
            opacity: !ComputerUse.hudHiddenForCapture && (hud.cardVisible || hud.showChip || ComputerUse.steerOpen) ? 1 : 0
            y: (hud.cardVisible || hud.showChip || ComputerUse.steerOpen) ? 0 : 12

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

        Column {
            width: parent.width
            spacing: 8

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
                height: visible ? (header.height + body.height + 8 + footer.height + hud.pad) : 0

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
            }

            Item {
                id: steerBox
                visible: ComputerUse.steerOpen && !ComputerUse.userHasControl
                width: parent.width
                height: visible ? 52 : 0

                StyledRect {
                    anchors.fill: parent
                    variant: "popup"
                    radius: Styling.popupRadius()
                    layer.enabled: true
                    layer.effect: Shadow {}
                }

                SearchInput {
                    id: steerInput
                    anchors.fill: parent
                    anchors.margins: 4
                    variant: "transparent"
                    placeholderText: qsTr("Steer the agent…")
                    clearOnEscape: false
                    onAccepted: hud.submitSteer()
                    onEscapePressed: ComputerUse.handleEscape()
                }
            }
        }
    }
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
