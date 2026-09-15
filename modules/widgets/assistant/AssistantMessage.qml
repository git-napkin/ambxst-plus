import QtQuick
import qs.modules.theme
import qs.modules.sidebar
import qs.config
import "message_content.js" as MessageContent

Column {
    id: root
    property var message: ({})
    property int messageIndex: -1
    width: parent ? parent.width : 200
    spacing: 8

    readonly property string role: message.role || ""
    readonly property bool isUser: role === "user"
    readonly property bool isAssistant: role === "assistant" || role === "system"
    readonly property bool isGate: role === "approval" || role === "diff" || role === "question"
    readonly property bool gateHidden: isGate && message.pending === false
    readonly property var parts: MessageContent.splitParts(String(message.content || ""))

    // Collapsed gates must not reserve ListView space (that caused intermittent gaps).
    visible: !gateHidden
    height: gateHidden ? 0 : implicitHeight
    clip: true

    ToolCallChip {
        width: parent.width
        visible: role === "tool_call"
        call: root.message
    }

    ComputerUseWorkChip {
        width: parent.width
        visible: role === "cu_work"
        message: root.message
    }

    ApprovalCard {
        width: parent.width
        visible: role === "approval" && message.pending !== false
        call: root.message
    }

    DiffPreviewCard {
        width: parent.width
        visible: role === "diff" && message.pending !== false
        call: root.message
    }

    QuestionCard {
        width: parent.width
        visible: role === "question" && message.pending !== false
        call: root.message
    }

    Row {
        id: bodyRow
        visible: root.isUser || root.isAssistant
        width: parent.width
        spacing: root.isUser ? 10 : 0

        Rectangle {
            visible: root.isUser
            width: 2
            height: Math.max(bodyCol.height, 12)
            radius: 1
            color: Colors.primary
            opacity: 0.55
        }

        Column {
            id: bodyCol
            width: bodyRow.width - (root.isUser ? 12 : 0)
            spacing: root.isUser ? 6 : 8

            Repeater {
                model: root.parts
                delegate: PartBlock {}
            }
        }
    }

    component PartBlock: Column {
        id: block
        required property var modelData
        width: parent ? parent.width : 100
        spacing: 0

        readonly property bool isText: !modelData.type || modelData.type === "text"
        readonly property bool isCode: modelData.type === "code"
        readonly property bool isMath: modelData.type === "math"
        readonly property bool isTable: modelData.type === "table"

        TextEdit {
            visible: block.isText && String(modelData.content || "").length > 0
            width: parent.width
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            textFormat: Text.RichText
            text: MessageContent.markdownToRichText(modelData.content || "", Config.theme.monoFont)
            color: root.isUser ? Colors.outline : Colors.overSurface
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(root.isUser ? -2 : -1)
            height: Math.max(contentHeight, 1)
        }

        CodeBlock {
            visible: block.isCode
            width: parent.width
            code: modelData.content || ""
            language: modelData.language || "text"
        }

        MathBlock {
            visible: block.isMath
            width: parent.width
            content: modelData.content || ""
            latex: modelData.latex || ""
        }

        MarkdownTable {
            visible: block.isTable
            width: parent.width
            headers: modelData.headers || []
            rows: modelData.rows || []
            aligns: modelData.aligns || []
        }
    }
}
