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
    signal openModelSelector
    signal requestClose

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
            return;
        }
        if (item.kind === "chat") {
            Ai.loadChat(item.id);
            searchInput.clear();
        }
    }

    function sendOrStop() {
        if (Ai.isLoading) {
            Ai.cancel();
            return;
        }
        const text = searchInput.text.trim();
        if (text.length === 0)
            return;
        Ai.sendMessage(text);
        searchInput.clear();
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 8

        Text {
            text: Icons.sparkle
            font.family: Icons.font
            font.pixelSize: Styling.fontSize(8)
            color: Styling.srItem("overprimary")
            Layout.alignment: Qt.AlignVCenter
        }

        SearchInput {
            id: searchInput
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.alignment: Qt.AlignVCenter
            variant: "common"
            placeholderText: qsTr("Ask Ambxst[+]…")
            clearOnEscape: false
            handleTabNavigation: true

            onAccepted: root.sendOrStop()
            onEscapePressed: root.requestClose()
            onCtrlRPressed: Ai.regenerateLast()
            onUpPressed: {
                if (searchInput.text.length === 0)
                    searchInput.text = Ai.lastUserMessage();
            }
        }

        Item {
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            Layout.alignment: Qt.AlignVCenter

            scale: sendArea.pressed ? 0.96 : 1
            Behavior on scale {
                enabled: Config.animDuration > 0
                NumberAnimation {
                    duration: Styling.animQuick
                    easing.type: Styling.animEasingOut
                }
            }

            StyledRect {
                anchors.fill: parent
                variant: sendArea.containsMouse ? "primaryfocus" : "primary"
                radius: Styling.radius(-2)
            }

            Text {
                anchors.centerIn: parent
                text: Ai.isLoading ? Icons.stop : Icons.paperPlane
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(2)
                color: Colors.overPrimary
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
