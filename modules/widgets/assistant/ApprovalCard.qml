import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config
import "message_content.js" as MessageContent

StyledRect {
    id: root
    property var call: ({})
    property string focusedAction: "reject"
    variant: "surface"
    radius: Styling.popupRadius() - 8
    implicitHeight: col.implicitHeight + 20
    implicitWidth: parent ? parent.width : 240

    readonly property string titleText: call.user_friendly_name || qsTr("Approve tool")
    readonly property string detailText: {
        if (call.name === "request_computer_use" && call.args && call.args.task_summary)
            return String(call.args.task_summary);
        if (call.name === "use_computer" && call.args)
            return String(call.args.action_summary || call.args.action || "");
        if (call.name === "run_shell_command" && call.args && call.args.command)
            return String(call.args.command);
        if (call.detail && String(call.detail).charAt(0) === "{")
            return "";
        return call.detail || "";
    }
    readonly property bool rejectHot: focusedAction === "reject"
    readonly property bool approveHot: focusedAction === "approve"

    onCallChanged: focusedAction = "reject"
    onVisibleChanged: if (visible)
        focusedAction = "reject"

    function confirmFocused() {
        if (!call || !call.call_id)
            return;
        if (focusedAction === "approve")
            Ai.approveTool(call.call_id);
        else
            Ai.rejectTool(call.call_id);
    }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 10
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: MessageContent.markdownToRichText(root.titleText, Config.theme.monoFont)
            textFormat: Text.RichText
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-1)
            font.weight: Font.Medium
            color: Colors.overSurface
            wrapMode: Text.Wrap
        }

        Text {
            Layout.fillWidth: true
            visible: root.detailText.length > 0
            text: root.detailText
            font.family: Config.theme.monoFont
            font.pixelSize: Styling.fontSize(-3)
            color: Colors.outline
            wrapMode: Text.Wrap
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

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Styling.tint(Colors.overError, Styling.hoverAlpha)
                    visible: root.rejectHot
                }

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
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: root.focusedAction = "reject"
                    onClicked: Ai.rejectTool(call.call_id)
                }

                Behavior on scale {
                    enabled: Config.animDuration > 0
                    NumberAnimation {
                        duration: Styling.animQuick
                        easing.type: Styling.animEasingOut
                    }
                }
            }

            StyledRect {
                variant: "primary"
                radius: Styling.radius(-4)
                implicitHeight: 28
                implicitWidth: acceptLabel.implicitWidth + 20
                scale: acceptArea.pressed ? 0.96 : 1

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: Styling.tint(Colors.overPrimary, Styling.hoverAlpha)
                    visible: root.approveHot
                }

                Text {
                    id: acceptLabel
                    anchors.centerIn: parent
                    text: qsTr("Approve")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.overPrimary
                }

                MouseArea {
                    id: acceptArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: root.focusedAction = "approve"
                    onClicked: Ai.approveTool(call.call_id)
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

        Text {
            Layout.fillWidth: true
            visible: ComputerUse.sessionActive
            text: qsTr("← → to choose · Enter to confirm")
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-4)
            color: Colors.outline
            horizontalAlignment: Text.AlignRight
        }
    }
}
