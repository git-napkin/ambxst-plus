import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.config

Item {
    id: root
    property var message: ({})
    property bool expanded: false
    readonly property string durationLabel: ComputerUse.formatWorkedDuration(message.durationMs)
    readonly property var items: message.items || []
    implicitHeight: body.implicitHeight
    implicitWidth: parent ? parent.width : 200

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 8

        Item {
            id: header
            Layout.fillWidth: true
            implicitHeight: headerRow.implicitHeight + 6

            RowLayout {
                id: headerRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Text {
                    text: root.expanded ? Icons.caretDown : Icons.caretRight
                    font.family: Icons.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.outline
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Worked for %1").arg(root.durationLabel)
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-3)
                    color: Colors.outline
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }
            }

            MouseArea {
                id: headerArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.expanded = !root.expanded
            }

            Rectangle {
                anchors.fill: parent
                radius: Styling.radius(-4)
                color: headerArea.containsMouse ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
                z: -1
            }
        }

        Column {
            visible: root.expanded
            Layout.fillWidth: true
            spacing: 10

            Repeater {
                model: root.expanded ? root.items : []
                delegate: Loader {
                    required property var modelData
                    width: parent.width
                    height: item ? item.implicitHeight : 0
                    source: Qt.resolvedUrl("AssistantMessage.qml")
                    onLoaded: {
                        item.width = Qt.binding(() => width);
                        item.message = modelData;
                        item.messageIndex = -1;
                    }
                }
            }
        }
    }
}
