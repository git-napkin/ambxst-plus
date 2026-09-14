pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.config
import qs.modules.theme

Item {
    id: root

    property string label: ""
    property string description: ""
    property bool stacked: false

    default property alias content: controlSlot.data

    implicitHeight: layout.implicitHeight
    implicitWidth: 200
    Layout.fillWidth: true
    Layout.preferredHeight: implicitHeight
    opacity: enabled ? 1 : 0.45

    GridLayout {
        id: layout
        width: parent.width
        columns: root.stacked ? 1 : 2
        columnSpacing: 12
        rowSpacing: 8

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            Layout.minimumWidth: 80
            spacing: 2

            Text {
                text: root.label
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(0)
                font.weight: Font.Medium
                color: Colors.overBackground
                wrapMode: Text.Wrap
                Layout.fillWidth: true
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
        }

        Item {
            id: controlSlot
            Layout.alignment: root.stacked ? Qt.AlignLeft : (Qt.AlignVCenter | Qt.AlignRight)
            Layout.fillWidth: root.stacked
            implicitWidth: children.length > 0 ? children[0].implicitWidth : 0
            implicitHeight: Math.max(40, children.length > 0 ? children[0].implicitHeight : 0)

            onWidthChanged: root.fitControl()
            onChildrenChanged: root.fitControl()
            Component.onCompleted: root.fitControl()
        }
    }

    function fitControl() {
        if (!root.stacked || controlSlot.children.length === 0)
            return;
        controlSlot.children[0].width = controlSlot.width;
    }
}
