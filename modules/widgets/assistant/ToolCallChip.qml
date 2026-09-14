import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config

StyledRect {
    id: root
    property var call: ({})
    variant: "surface"
    radius: Styling.popupRadius() - 8
    implicitHeight: expanded ? body.implicitHeight + 20 : 36
    implicitWidth: parent ? parent.width : 200

    property bool expanded: false

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: Icons.circuitry
                font.family: Icons.font
                font.pixelSize: Styling.fontSize(0)
                color: Styling.srItem("overprimary")
            }

            Text {
                Layout.fillWidth: true
                text: root.call.user_friendly_name || root.call.name || qsTr("Tool")
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-2)
                color: Colors.overSurface
                elide: Text.ElideRight
            }

            Text {
                text: root.call.status || (Ai.isLoading ? qsTr("running") : qsTr("done"))
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-4)
                color: Colors.outline
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
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.expanded = !root.expanded
    }
}
