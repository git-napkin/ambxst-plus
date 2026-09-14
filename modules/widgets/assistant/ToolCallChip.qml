import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

Item {
    id: root
    property var call: ({})
    property bool expanded: false
    implicitHeight: body.implicitHeight
    implicitWidth: parent ? parent.width : 200

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: root.expanded ? Icons.caretDown : Icons.caretRight
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(-2)
                color: Colors.outline
            }

            Text {
                Layout.fillWidth: true
                text: root.call.user_friendly_name || root.call.name || qsTr("Tool")
                font.family: Config.theme.monoFont
                font.pixelSize: Styling.fontSize(-3)
                color: Colors.outline
                elide: Text.ElideRight
            }

            Text {
                text: root.call.status || (Ai.isLoading ? qsTr("running") : qsTr("done"))
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-4)
                font.weight: Font.Medium
                color: Colors.outline
                opacity: 0.8
            }
        }

        Text {
            visible: root.expanded
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.family: Config.theme.monoFont
            font.pixelSize: Styling.fontSize(-4)
            color: Colors.outline
            text: JSON.stringify(root.call.args || {}, null, 2)
        }

        Text {
            visible: root.expanded && root.call.result
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.family: Config.theme.monoFont
            font.pixelSize: Styling.fontSize(-4)
            color: Colors.overSurface
            text: typeof root.call.result === "string" ? root.call.result : JSON.stringify(root.call.result, null, 2)
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.expanded = !root.expanded
    }

    Rectangle {
        anchors.fill: parent
        radius: Styling.radius(-4)
        color: area.containsMouse ? Styling.tint(Colors.overSurface, Styling.hoverAlpha) : "transparent"
        z: -1
    }
}
