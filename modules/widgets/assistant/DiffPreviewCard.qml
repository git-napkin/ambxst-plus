import QtQuick
import QtQuick.Layouts
import qs.modules.theme
import qs.modules.services
import qs.modules.components
import qs.modules.sidebar
import qs.config
import "message_content.js" as MessageContent

StyledRect {
    id: root
    property var call: ({})
    variant: "surface"
    radius: Styling.popupRadius() - 8
    implicitHeight: col.implicitHeight + 20
    implicitWidth: parent ? parent.width : 240

    function langFromFile(path) {
        const name = String(path || "").split("/").pop() || "";
        const dot = name.lastIndexOf(".");
        if (dot < 0)
            return "text";
        const ext = name.slice(dot + 1).toLowerCase();
        const map = {
            py: "python",
            js: "javascript",
            ts: "typescript",
            tsx: "typescript",
            jsx: "javascript",
            qml: "qml",
            sh: "bash",
            bash: "bash",
            zsh: "bash",
            md: "markdown",
            json: "json",
            nix: "nix",
            rs: "rust",
            go: "go",
            css: "css",
            html: "html",
            toml: "toml",
            yaml: "yaml",
            yml: "yaml"
        };
        return map[ext] || ext || "text";
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
            text: MessageContent.markdownToRichText(call.user_friendly_name || qsTr("Review file edits"), Config.theme.monoFont)
            textFormat: Text.RichText
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-1)
            font.weight: Font.Medium
            color: Colors.overSurface
            wrapMode: Text.Wrap
        }

        Repeater {
            model: call.previews || []
            delegate: ColumnLayout {
                id: previewBlock
                required property var modelData
                Layout.fillWidth: true
                spacing: 4

                readonly property string kind: modelData.kind || ""
                readonly property string fileName: modelData.file || modelData.path || qsTr("file")
                readonly property bool showContent: kind === "create" && !!(modelData.content && String(modelData.content).length)
                readonly property string previewCode: {
                    if (previewBlock.showContent)
                        return String(modelData.content);
                    return modelData.unified_diff || modelData.diff || modelData.preview || modelData.content || "";
                }
                readonly property string previewLang: previewBlock.showContent
                    ? root.langFromFile(previewBlock.fileName)
                    : "diff"

                Text {
                    text: previewBlock.fileName
                    font.family: Config.theme.monoFont
                    font.pixelSize: Styling.fontSize(-3)
                    color: Styling.srItem("overprimary")
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                CodeBlock {
                    Layout.fillWidth: true
                    visible: previewBlock.previewCode.length > 0
                    code: previewBlock.previewCode
                    language: previewBlock.previewLang
                }

                Text {
                    visible: previewBlock.previewCode.length === 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-3)
                    color: Colors.outline
                    text: qsTr("No preview available for this edit.")
                }
            }
        }

        Text {
            visible: !(call.previews && call.previews.length)
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-3)
            color: Colors.outline
            text: qsTr("No file preview was generated for this edit.")
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
