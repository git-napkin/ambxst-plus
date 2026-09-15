import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

StyledRect {
    id: root
    variant: "popup"
    radius: Styling.popupRadius()

    property alias inputText: searchInput.text
    property bool idleOpen: false
    property int idleSelected: -1
    signal openModelSelector
    signal requestClose
    signal idleActivate
    signal idleMove(int delta)

    layer.enabled: true
    layer.effect: Shadow {}

    function focusInput() {
        searchInput.focusInput();
    }

    function activateIdle(item) {
        if (!item)
            return;
        if (item.kind === "slash") {
            if (item.id === "/model") {
                root.openModelSelector();
                return;
            }
            Ai.sendMessage(item.id);
            searchInput.clear();
            return;
        }
        if (item.kind === "command") {
            Ai.sendMessage(item.prompt || "");
            searchInput.clear();
        }
    }

    function sendOrStop() {
        if (Ai.isLoading) {
            Ai.cancel();
            return;
        }
        const text = searchInput.text.trim();
        if (text.length === 0 || text === "/") {
            if (root.idleOpen && root.idleSelected >= 0) {
                root.idleActivate();
                return;
            }
            if (text.length === 0)
                return;
        }
        Ai.sendMessage(text);
        searchInput.clear();
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 8

        SearchInput {
            id: searchInput
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.alignment: Qt.AlignVCenter
            variant: "transparent"
            placeholderText: qsTr("Ask or type /")
            clearOnEscape: false
            handleTabNavigation: true

            onAccepted: root.sendOrStop()
            onEscapePressed: root.requestClose()
            onCtrlRPressed: Ai.regenerateLast()
            onDownPressed: root.idleMove(1)
            onUpPressed: {
                if (root.idleOpen) {
                    root.idleMove(-1);
                    return;
                }
                if (searchInput.text.length === 0)
                    searchInput.text = Ai.lastUserMessage();
            }
        }

        Text {
            Layout.alignment: Qt.AlignVCenter
            Layout.maximumWidth: 148
            Layout.preferredHeight: 40
            verticalAlignment: Text.AlignVCenter
            text: Ai.currentModel ? Ai.currentModel.name : qsTr("Model")
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-3)
            color: modelArea.containsMouse ? Colors.overSurface : Colors.outline
            elide: Text.ElideRight

            MouseArea {
                id: modelArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openModelSelector()
            }
        }

        StyledRect {
            id: allowChip
            Layout.alignment: Qt.AlignVCenter
            Layout.preferredHeight: 28
            implicitWidth: allowRow.implicitWidth + 16
            radius: Styling.radius(-4)
            variant: Ai.autoApprove ? "primary" : "internalbg"
            scale: autoArea.pressed ? 0.96 : 1
            opacity: autoArea.containsMouse || Ai.autoApprove ? 1 : 0.85

            Behavior on scale {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }
            Behavior on opacity {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }

            Row {
                id: allowRow
                anchors.centerIn: parent
                spacing: 5

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Ai.autoApprove ? Icons.lightning : Icons.shieldCheck
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Ai.autoApprove ? Colors.overPrimary : Colors.outline
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Ai.autoApprove ? qsTr("Allow all") : qsTr("Auto-review")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-3)
                    font.weight: Font.Medium
                    color: Ai.autoApprove ? Colors.overPrimary : Colors.outline
                }
            }

            MouseArea {
                id: autoArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: Ai.setAutoApprove(!Ai.autoApprove)
            }

            StyledToolTip {
                tooltipText: Ai.autoApprove ? qsTr("Allow all for this chat") : qsTr("Auto-review")
                description: Ai.autoApprove
                    ? qsTr("Commands and tool actions run without asking. Click to require review again.")
                    : qsTr("Safe actions may run; anything else asks first. Click to allow all for this chat only.")
                show: autoArea.containsMouse
            }
        }

        Item {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            Layout.alignment: Qt.AlignVCenter

            scale: sendArea.pressed ? 0.96 : 1
            opacity: Ai.isLoading || searchInput.text.length > 0 ? 1 : 0.4
            Behavior on scale {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }
            Behavior on opacity {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }

            Text {
                anchors.centerIn: parent
                text: Ai.isLoading ? Icons.stop : Icons.enter
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(2)
                color: Ai.isLoading ? Colors.overSurface : Colors.outline
            }

            MouseArea {
                id: sendArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.sendOrStop()
            }
        }
    }
}
