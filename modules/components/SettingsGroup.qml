pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme
import qs.modules.components

Item {
    id: root

    property string title: ""
    property string description: ""
    default property alias content: body.data

    implicitHeight: col.implicitHeight
    implicitWidth: 200
    Layout.fillWidth: true
    Layout.preferredHeight: implicitHeight

    ColumnLayout {
        id: col
        width: parent.width
        spacing: 8

        Text {
            visible: root.title !== ""
            text: root.title
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(2)
            font.weight: Font.DemiBold
            color: Colors.overBackground
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Text {
            visible: root.description !== ""
            text: root.description
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-2)
            color: Colors.overSurfaceVariant
            opacity: 0.8
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        StyledRect {
            Layout.fillWidth: true
            variant: "pane"
            radius: Styling.radius(0)
            implicitHeight: body.implicitHeight + 16
            clip: true

            ColumnLayout {
                id: body
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 8
                spacing: 4
            }
        }
    }
}
