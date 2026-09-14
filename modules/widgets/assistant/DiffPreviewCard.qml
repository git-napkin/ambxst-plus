import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.modules.sidebar
import qs.config

StyledRect {
    id: root
    property var call: ({})
    variant: "surface"
    radius: Styling.popupRadius() - 8
    implicitHeight: col.implicitHeight + 20
    implicitWidth: parent ? parent.width : 240

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: call.user_friendly_name || qsTr("Review file edits")
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-1)
            font.weight: Font.Medium
            color: Colors.overSurface
            wrapMode: Text.Wrap
        }

        Repeater {
            model: call.previews || []
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: modelData.file || modelData.path || qsTr("file")
                    font.family: Config.theme.monoFont
                    font.pixelSize: Styling.fontSize(-3)
                    color: Styling.srItem("overprimary")
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                CodeBlock {
                    Layout.fillWidth: true
                    code: modelData.diff || modelData.preview || ""
                    language: "diff"
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Item { Layout.fillWidth: true }

            StyledRect {
                variant: "error"
                radius: Styling.radius(-4)
                implicitHeight: 28
                implicitWidth: rejectLabel.implicitWidth + 20
                scale: rejectArea.pressed ? 0.96 : 1

                Text {
                    id: rejectLabel
                    anchors.centerIn: parent
                    text: qsTr("Reject")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.overError
                }

                MouseArea {
                    id: rejectArea
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Ai.rejectTool(call.call_id)
                }
            }

            StyledRect {
                variant: "primary"
                radius: Styling.radius(-4)
                implicitHeight: 28
                implicitWidth: acceptLabel.implicitWidth + 20
                scale: acceptArea.pressed ? 0.96 : 1

                Text {
                    id: acceptLabel
                    anchors.centerIn: parent
                    text: qsTr("Accept")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.overPrimary
                }

                MouseArea {
                    id: acceptArea
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Ai.approveTool(call.call_id)
                }
            }
        }
    }
}
