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

    readonly property bool drivingKeys: ComputerUse.sessionActive && !ComputerUse.userHasControl && !ComputerUse.injectingInput
    readonly property bool showWait: ComputerUse.waiting && !Ai.approvalPending
    readonly property bool pointerChrome: ComputerUse.userHasControl

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
    readonly property bool clickThrough: !hud.cardVisible && !hud.showChip && !ComputerUse.steerOpen && ComputerUse.sessionState !== "approvalWait"
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
    onAssistantTextChanged: {
        hud.refreshPresence();
        hud.bumpHideTimer();
    }
    onShowWaitChanged: hud.refreshPresence()

    function claimKeys() {
        if (!hud.drivingKeys)
            return;
        if (hud.requestActivate)
            hud.requestActivate();
        if (ComputerUse.steerOpen) {
            if (!steerInput.inputActive)
                steerInput.focusInput();
            return;
        }
        if (!keySink.activeFocus)
            keySink.forceActiveFocus();
    }

    function printableFromEvent(event) {
        const raw = event.text || "";
        if (raw.length && raw.charCodeAt(0) >= 32)
            return raw;
        const k = event.key;
        if (k === Qt.Key_Space)
            return " ";
        if (k >= Qt.Key_A && k <= Qt.Key_Z) {
            const c = String.fromCharCode(65 + (k - Qt.Key_A));
            return (event.modifiers & Qt.ShiftModifier) ? c : c.toLowerCase();
        }
        if (k >= Qt.Key_0 && k <= Qt.Key_9)
            return String.fromCharCode(48 + (k - Qt.Key_0));
        return "";
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
        const k = event.key;
        if (k === Qt.Key_Escape || k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Tab)
            return;
        if (k === Qt.Key_Shift || k === Qt.Key_Control || k === Qt.Key_Alt || k === Qt.Key_Meta || k === Qt.Key_AltGr)
            return;
        if (k === Qt.Key_CapsLock || k === Qt.Key_NumLock || k === Qt.Key_ScrollLock)
            return;
        if (k === Qt.Key_Left || k === Qt.Key_Right || k === Qt.Key_Up || k === Qt.Key_Down)
            return;
        if (k === Qt.Key_Home || k === Qt.Key_End || k === Qt.Key_PageUp || k === Qt.Key_PageDown)
            return;
        if (k === Qt.Key_Insert || k === Qt.Key_Delete || k === Qt.Key_Print || k === Qt.Key_Pause)
            return;
        if (k >= Qt.Key_F1 && k <= Qt.Key_F35)
            return;
        if (k === Qt.Key_Backspace) {
            hud.openSteer("");
            event.accepted = true;
            return;
        }
        const ch = hud.printableFromEvent(event);
        hud.openSteer(ch);
        event.accepted = true;
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
        if (!ComputerUse.sessionActive) {
            hud.cardVisible = false;
            hideTimer.stop();
            return;
        }
        if (ComputerUse.hudHiddenForCapture) {
            hud.cardVisible = false;
            return;
        }
        if (Ai.approvalPending) {
            ComputerUse.hudCollapsed = false;
            hud.cardVisible = true;
            hideTimer.stop();
            return;
        }
        if (ComputerUse.waiting) {
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
            hideTimer.stop();
            return;
        }
        hud.cardVisible = true;
    }

    function bumpHideTimer() {
        if (!hud.cardVisible || Ai.approvalPending || ComputerUse.waiting)
            return;
        hideTimer.restart();
    }

    FocusGrab {
        id: focusGrab
        windows: [hud]
        active: ComputerUse.sessionState === "approvalWait"
    }

    Timer {
        id: hideTimer
        interval: 2500
        repeat: false
        onTriggered: {
            if (Ai.approvalPending || ComputerUse.waiting)
                return;
            hud.cardVisible = false;
        }
    }

    Timer {
        id: claimTimer
        interval: 250
        repeat: true
        running: hud.drivingKeys
        onTriggered: hud.claimKeys()
    }

    Shortcut {
        sequences: ["Escape"]
        enabled: hud.drivingKeys
        context: Qt.ApplicationShortcut
        onActivated: ComputerUse.handleEscape()
    }

    Connections {
        target: Ai
        function onLastHudActivityAtChanged() {
            ComputerUse.hudCollapsed = false;
            hud.refreshPresence();
            hud.bumpHideTimer();
        }
        function onApprovalPendingChanged() {
            hud.refreshPresence();
            hud.bumpHideTimer();
            if (Ai.approvalPending)
                hud.claimKeys();
        }
        function onChatModelChanged() {
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
        function onWaitingChanged() {
            hud.refreshPresence();
            hud.bumpHideTimer();
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
        id: keySink
        // Fullscreen key sink so Exclusive keyboard still reaches Qt after the
        // pointer mask shrinks to a 1px click-through hole (Quickshell Region mask).
        anchors.fill: parent
        z: 1
        focus: hud.drivingKeys
        Keys.enabled: hud.drivingKeys
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

        Item {
            id: hudAnchor
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
                height: {
                    if (!visible)
                        return 0;
                    let h = header.height + body.height + hud.pad;
                    if (footer.visible)
                        h += 8 + footer.height;
                    else
                        h += hud.pad;
                    return h;
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
                    visible: hud.pointerChrome
                    enabled: hud.pointerChrome
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
                    height: hud.steerText.length && !Ai.approvalPending && !hud.showWait ? 28 : 0

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
                        if (hud.showWait)
                            return Math.max(32, waitLabel.implicitHeight);
                        return Math.min(markdown.implicitHeight, hud.bodyMax);
                    }
                    clip: true

                    ApprovalCard {
                        id: approvalLoader
                        visible: Ai.approvalPending
                        width: parent.width
                        call: Ai.pendingApproval || ({})
                    }

                    Text {
                        id: waitLabel
                        visible: hud.showWait
                        width: parent.width
                        text: qsTr("Waiting for %1s").arg(ComputerUse.waitSecondsLeft)
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-1)
                        font.weight: Font.Medium
                        color: Colors.overSurface
                        wrapMode: Text.NoWrap
                    }

                    AssistantMessage {
                        id: markdown
                        visible: !Ai.approvalPending && !hud.showWait
                        width: parent.width
                        message: ({
                                role: "assistant",
                                content: hud.assistantText
                            })
                    }

                    Rectangle {
                        visible: !Ai.approvalPending && !hud.showWait && markdown.implicitHeight > body.height
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
                    visible: hud.pointerChrome
                    anchors.top: body.bottom
                    anchors.topMargin: visible ? 8 : 0
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 4
                    anchors.rightMargin: 4
                    height: visible ? 40 : 0

                    RowLayout {
                        anchors.fill: parent
                        spacing: 2

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

                        Item { Layout.fillWidth: true }
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
