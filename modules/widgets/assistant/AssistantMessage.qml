import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.modules.sidebar
import qs.config

ColumnLayout {
    id: root
    property var message: ({})
    property int messageIndex: -1
    spacing: 6

    readonly property string role: message.role || ""
    readonly property bool isUser: role === "user"
    readonly property bool isAssistant: role === "assistant" || role === "system"

    ToolCallChip {
        Layout.fillWidth: true
        visible: role === "tool_call"
        call: root.message
    }

    ApprovalCard {
        Layout.fillWidth: true
        visible: role === "approval"
        call: root.message
    }

    DiffPreviewCard {
        Layout.fillWidth: true
        visible: role === "diff"
        call: root.message
    }

    QuestionCard {
        Layout.fillWidth: true
        visible: role === "question"
        call: root.message
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.isUser || root.isAssistant
        layoutDirection: root.isUser ? Qt.RightToLeft : Qt.LeftToRight
        spacing: 8

        Item {
            Layout.fillWidth: true
            visible: root.isUser
        }

        StyledRect {
            Layout.maximumWidth: root.width * 0.92
            Layout.fillWidth: true
            implicitHeight: bubbleCol.implicitHeight + 20
            variant: root.isUser ? "primary" : "surface"
            radius: Styling.popupRadius() - 8

            ColumnLayout {
                id: bubbleCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 10
                spacing: 8

                Repeater {
                    model: root._parts()
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 0

                        TextEdit {
                            Layout.fillWidth: true
                            visible: modelData.type === "text" && (modelData.content || "").length > 0
                            readOnly: true
                            wrapMode: TextEdit.Wrap
                            textFormat: Text.MarkdownText
                            text: modelData.content || ""
                            color: root.isUser ? Colors.overPrimary : Colors.overSurface
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-1)
                            selectByMouse: true
                        }

                        CodeBlock {
                            Layout.fillWidth: true
                            visible: modelData.type === "code"
                            code: modelData.content || ""
                            language: modelData.language || "text"
                        }
                    }
                }
            }
        }
    }

    function _parts() {
        const txt = String(root.message.content || "");
        const parts = [];
        const regex = /```(\w*)\n([\s\S]*?)```/g;
        let lastIndex = 0;
        let match;
        while ((match = regex.exec(txt)) !== null) {
            if (match.index > lastIndex) {
                parts.push({
                    type: "text",
                    content: txt.substring(lastIndex, match.index),
                    language: ""
                });
            }
            parts.push({
                type: "code",
                content: match[2].trim(),
                language: match[1] || "text"
            });
            lastIndex = regex.lastIndex;
        }
        if (parts.length === 0 || lastIndex < txt.length) {
            parts.push({
                type: "text",
                content: lastIndex < txt.length ? txt.substring(lastIndex) : (parts.length === 0 ? txt : ""),
                language: ""
            });
        }
        return parts;
    }
}
