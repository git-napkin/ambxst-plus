import QtQuick
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

StyledRect {
    id: root
    variant: "popup"
    radius: Styling.popupRadius()

    property int contentHeight: list.contentHeight + (compact ? 16 : 24)
    property bool compact: false

    layer.enabled: true
    layer.effect: Shadow {}

    ListView {
        id: list
        anchors.fill: parent
        anchors.margins: root.compact ? 8 : 12
        clip: true
    spacing: 10
    model: Ai.currentChat
    boundsBehavior: Flickable.StopAtBounds

    delegate: AssistantMessage {
        required property var modelData
        required property int index
        width: list.width
        message: modelData
        messageIndex: index
    }

        onCountChanged: Qt.callLater(() => list.positionViewAtEnd())
        onContentHeightChanged: {
            if (list.atYEnd || Ai.isLoading)
                Qt.callLater(() => list.positionViewAtEnd());
        }
    }

    Connections {
        target: Ai
        function onChatModelChanged() {
            Qt.callLater(() => list.positionViewAtEnd());
        }
    }
}
