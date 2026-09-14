import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.config
import "message_content.js" as MessageContent

Item {
    id: root
    property var call: ({})
    property bool expanded: false
    readonly property bool isRunning: call.status === "running" || (!call.status && Ai.isLoading)
    readonly property string label: {
        if (root.isRunning)
            return call.user_friendly_name || call.name || qsTr("Working");
        return call.user_friendly_done || call.user_friendly_name || call.name || qsTr("Done");
    }
    readonly property string previewPath: {
        if (call.previewPath)
            return String(call.previewPath);
        const result = call.result || {};
        if (result.path)
            return String(result.path);
        if (result.screenshot && result.screenshot.path)
            return String(result.screenshot.path);
        return "";
    }
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
                text: MessageContent.markdownToRichText(root.label, Config.theme.monoFont)
                textFormat: Text.RichText
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-3)
                color: Colors.outline
                elide: Text.ElideRight
                maximumLineCount: 1
            }
        }

        Image {
            visible: root.previewPath.length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            sourceSize.width: 160
            sourceSize.height: 72
            source: root.previewPath.length ? ("file://" + root.previewPath) : ""
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
