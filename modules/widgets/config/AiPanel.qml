import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.modules.theme
import qs.modules.components
import qs.modules.services
import qs.config

Item {
    id: root

    property int maxContentWidth: 480
    readonly property int contentWidth: Math.min(width, maxContentWidth)
    readonly property real sideMargin: Math.max(0, (width - contentWidth) / 2)

    Flickable {
        anchors.fill: parent
        contentHeight: contentColumn.implicitHeight + 40
        clip: true
        bottomMargin: 40

        ColumnLayout {
            id: contentColumn
            width: root.contentWidth
            x: root.sideMargin
            y: 20
            spacing: 24

            Text {
                text: "AI & API Keys"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(10)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.bottomMargin: 8
            }

            Text {
                text: "Overlay"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(2)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
            }

            Text {
                text: "Workspace"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            TextField {
                id: workspaceInput
                Layout.fillWidth: true
                text: Config.ai.workspace || ""
                placeholderText: Quickshell.env("HOME") || qsTr("Project folder")
                font.family: Config.theme.font
                color: Colors.overSurface
                onEditingFinished: Config.ai.workspace = text
                background: StyledRect {
                    variant: "internalbg"
                    radius: Styling.radius(4)
                }
            }

            Text {
                text: "System prompt"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            TextArea {
                id: promptInput
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                wrapMode: Text.Wrap
                text: Config.ai.systemPrompt || ""
                font.family: Config.theme.font
                color: Colors.overSurface
                onEditingFinished: Config.ai.systemPrompt = text
                background: StyledRect { variant: "internalbg"; radius: Styling.radius(4) }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Width"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.outline
                    }
                    SpinBox {
                        from: 400
                        to: 1200
                        stepSize: 20
                        value: Config.ai.overlayWidth || 640
                        onValueModified: Config.ai.overlayWidth = value
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Vertical position"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.outline
                    }
                    Slider {
                        from: 0.05
                        to: 0.5
                        value: Config.ai.overlayYFraction ?? 0.22
                        onMoved: Config.ai.overlayYFraction = value
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Show scrim"
                    font.family: Config.theme.font
                    color: Colors.overSurface
                    Layout.fillWidth: true
                }
                Switch {
                    checked: Config.ai.showScrim ?? true
                    onToggled: Config.ai.showScrim = checked
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Temperature"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.outline
                    }
                    Slider {
                        from: 0
                        to: 2
                        value: Config.ai.temperature ?? 0.7
                        onMoved: Config.ai.temperature = value
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Max tokens"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.outline
                    }
                    SpinBox {
                        from: 256
                        to: 128000
                        stepSize: 256
                        value: Config.ai.maxTokens || 4096
                        onValueModified: Config.ai.maxTokens = value
                    }
                }
            }

            Text {
                text: "Execution profile"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(2)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.topMargin: 8
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "Read files"
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overSurface
                }
                RowLayout {
                    Layout.fillWidth: true
                    Repeater {
                        model: ["AgentDecides", "AlwaysAllow", "AlwaysAsk"]
                        delegate: StyledRect {
                            required property string modelData
                            variant: Config.ai.executionProfile.readFiles === modelData ? "primary" : "internalbg"
                            radius: Styling.radius(-4)
                            implicitHeight: 28
                            implicitWidth: readLab.implicitWidth + 16
                            Text {
                                id: readLab
                                anchors.centerIn: parent
                                text: modelData
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(-3)
                                color: Config.ai.executionProfile.readFiles === modelData ? Colors.overPrimary : Colors.overSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Config.ai.executionProfile.readFiles = modelData
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "Apply diffs"
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overSurface
                }
                RowLayout {
                    Layout.fillWidth: true
                    Repeater {
                        model: ["AgentDecides", "AlwaysAllow", "AlwaysAsk"]
                        delegate: StyledRect {
                            required property string modelData
                            variant: Config.ai.executionProfile.applyCodeDiffs === modelData ? "primary" : "internalbg"
                            radius: Styling.radius(-4)
                            implicitHeight: 28
                            implicitWidth: diffLab.implicitWidth + 16
                            Text {
                                id: diffLab
                                anchors.centerIn: parent
                                text: modelData
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(-3)
                                color: Config.ai.executionProfile.applyCodeDiffs === modelData ? Colors.overPrimary : Colors.overSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Config.ai.executionProfile.applyCodeDiffs = modelData
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "Shell commands"
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overSurface
                }
                RowLayout {
                    Layout.fillWidth: true
                    Repeater {
                        model: ["AgentDecides", "AlwaysAllow", "AlwaysAsk"]
                        delegate: StyledRect {
                            required property string modelData
                            variant: Config.ai.executionProfile.executeCommands === modelData ? "primary" : "internalbg"
                            radius: Styling.radius(-4)
                            implicitHeight: 28
                            implicitWidth: shLab.implicitWidth + 16
                            Text {
                                id: shLab
                                anchors.centerIn: parent
                                text: modelData
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(-3)
                                color: Config.ai.executionProfile.executeCommands === modelData ? Colors.overPrimary : Colors.overSurface
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: Config.ai.executionProfile.executeCommands = modelData
                            }
                        }
                    }
                }
            }

            Text {
                text: "Ask user questions"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: ["AlwaysAsk", "AskExceptInAutoApprove", "Never"]
                    delegate: StyledRect {
                        required property string modelData
                        variant: Config.ai.executionProfile.askUserQuestion === modelData ? "primary" : "internalbg"
                        radius: Styling.radius(-4)
                        implicitHeight: 28
                        implicitWidth: qLab.implicitWidth + 16
                        Text {
                            id: qLab
                            anchors.centerIn: parent
                            text: modelData
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-3)
                            color: Config.ai.executionProfile.askUserQuestion === modelData ? Colors.overPrimary : Colors.overSurface
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Config.ai.executionProfile.askUserQuestion = modelData
                        }
                    }
                }
            }

            Text {
                text: "Computer use"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: ["Never", "AlwaysAsk", "AlwaysAllow"]
                    delegate: StyledRect {
                        required property string modelData
                        variant: Config.ai.executionProfile.computerUse === modelData ? "primary" : "internalbg"
                        radius: Styling.radius(-4)
                        implicitHeight: 28
                        implicitWidth: cLab.implicitWidth + 16
                        Text {
                            id: cLab
                            anchors.centerIn: parent
                            text: modelData
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-3)
                            color: Config.ai.executionProfile.computerUse === modelData ? Colors.overPrimary : Colors.overSurface
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Config.ai.executionProfile.computerUse = modelData
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Web search (Exa)"
                    font.family: Config.theme.font
                    color: Colors.overSurface
                    Layout.fillWidth: true
                }
                Switch {
                    checked: Config.ai.executionProfile.webSearchEnabled ?? true
                    onToggled: Config.ai.executionProfile.webSearchEnabled = checked
                }
            }

            Text {
                text: "Command allowlist (one regex per line)"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                wrapMode: Text.Wrap
                font.family: Config.theme.monoFont
                font.pixelSize: Styling.fontSize(-2)
                color: Colors.overSurface
                text: (Config.ai.executionProfile.commandAllowlist || []).join("\n")
                onEditingFinished: Config.ai.executionProfile.commandAllowlist = text.split("\n").map(s => s.trim()).filter(s => s.length)
                background: StyledRect { variant: "internalbg"; radius: Styling.radius(4) }
            }

            Text {
                text: "Command denylist (one regex per line)"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(-1)
                color: Colors.overSurface
            }
            TextArea {
                Layout.fillWidth: true
                Layout.preferredHeight: 80
                wrapMode: Text.Wrap
                font.family: Config.theme.monoFont
                font.pixelSize: Styling.fontSize(-2)
                color: Colors.overSurface
                text: (Config.ai.executionProfile.commandDenylist || []).join("\n")
                onEditingFinished: Config.ai.executionProfile.commandDenylist = text.split("\n").map(s => s.trim()).filter(s => s.length)
                background: StyledRect { variant: "internalbg"; radius: Styling.radius(4) }
            }

            Text {
                text: "Enabled tools"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(2)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.topMargin: 8
            }

            Repeater {
                model: ["read_files", "grep", "file_glob", "apply_file_diffs", "run_shell_command", "ask_user_question", "read_skill", "exa_search", "exa_contents", "native"]
                delegate: RowLayout {
                    required property string modelData
                    Layout.fillWidth: true
                    Text {
                        text: modelData
                        font.family: Config.theme.monoFont
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.overSurface
                        Layout.fillWidth: true
                    }
                    Switch {
                        checked: (Config.ai.enabledTools || []).indexOf(modelData) !== -1
                        onToggled: {
                            const cur = (Config.ai.enabledTools || []).slice();
                            const i = cur.indexOf(modelData);
                            if (checked && i === -1)
                                cur.push(modelData);
                            if (!checked && i !== -1)
                                cur.splice(i, 1);
                            Config.ai.enabledTools = cur;
                        }
                    }
                }
            }

            Text {
                text: "Context"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(2)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.topMargin: 8
            }

            Repeater {
                model: [
                    { key: "focusedWindow", label: "Focused window" },
                    { key: "clipboard", label: "Clipboard" },
                    { key: "notifications", label: "Notifications" },
                    { key: "weather", label: "Weather" },
                    { key: "resources", label: "Resources" }
                ]
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Text {
                        text: modelData.label
                        font.family: Config.theme.font
                        color: Colors.overSurface
                        Layout.fillWidth: true
                    }
                    Switch {
                        checked: Config.ai.contextProviders[modelData.key] ?? false
                        onToggled: Config.ai.contextProviders[modelData.key] = checked
                    }
                }
            }

            Text {
                text: "Saved commands"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(2)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.topMargin: 8
            }

            Repeater {
                model: Config.ai.commands || []
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: (modelData.name || modelData.id || qsTr("Command"))
                        font.family: Config.theme.font
                        color: Colors.overSurface
                        elide: Text.ElideRight
                    }
                    Button {
                        text: qsTr("Remove")
                        onClicked: {
                            const next = (Config.ai.commands || []).slice();
                            next.splice(index, 1);
                            Config.ai.commands = next;
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: newCmdName
                    Layout.fillWidth: true
                    placeholderText: qsTr("Name")
                    font.family: Config.theme.font
                    color: Colors.overSurface
                    background: StyledRect { variant: "internalbg"; radius: Styling.radius(4) }
                }
                TextField {
                    id: newCmdPrompt
                    Layout.fillWidth: true
                    placeholderText: qsTr("Prompt")
                    font.family: Config.theme.font
                    color: Colors.overSurface
                    background: StyledRect { variant: "internalbg"; radius: Styling.radius(4) }
                }
                Button {
                    text: qsTr("Add")
                    onClicked: {
                        if (!newCmdName.text.trim() || !newCmdPrompt.text.trim())
                            return;
                        const next = (Config.ai.commands || []).slice();
                        next.push({
                            id: newCmdName.text.trim().toLowerCase().replace(/\s+/g, "-"),
                            name: newCmdName.text.trim(),
                            prompt: newCmdPrompt.text.trim()
                        });
                        Config.ai.commands = next;
                        newCmdName.text = "";
                        newCmdPrompt.text = "";
                    }
                }
            }

            // Providers
            Repeater {
                model: ["gemini", "openai", "anthropic", "mistral", "groq", "ollama", "minimax", "exa"]
                delegate: StyledRect {
                    required property string modelData
                    Layout.fillWidth: true
                    variant: "surface"
                    radius: Styling.radius(8)
                    
                    // We need a wrapper to give it a height based on content
                    implicitHeight: providerCol.implicitHeight + 32

                    ColumnLayout {
                        id: providerCol
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 12

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(2)
                                font.weight: Font.Bold
                                color: Colors.overSurface
                                Layout.fillWidth: true
                            }
                            Text {
                                text: KeyStore.hasKey(modelData) ? "Key Configured" : "Not Configured"
                                font.family: Config.theme.font
                                font.pixelSize: Styling.fontSize(-2)
                                color: KeyStore.hasKey(modelData) ? Colors.success : Colors.outline
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            TextField {
                                visible: modelData !== "ollama"
                                id: keyInput
                                Layout.fillWidth: true
                                placeholderText: "Enter API Key..."
                                echoMode: TextInput.Password
                                font.family: Config.theme.font
                                color: Colors.overSurface
                                padding: 6
                                
                                background: StyledRect {
                                    variant: "internalbg"
                                    radius: Styling.radius(4)
                                    border.width: keyInput.activeFocus ? 2 : 0
                                    border.color: Styling.srItem("primary")
                                    anchors.fill: parent
                                    anchors.leftMargin: -parent.padding
                                    anchors.rightMargin: -parent.padding
                                    anchors.topMargin: -parent.padding
                                    anchors.bottomMargin: -parent.padding
                                }
                            }
                            Button {
                                id: saveButton
                                text: modelData === "ollama" ? (KeyStore.hasKey("ollama") ? "Configured" : "Enable") : "Save"
                                visible: modelData === "ollama" ? !KeyStore.hasKey("ollama") : true
                                hoverEnabled: true
                                leftPadding: 6
                                rightPadding: 6
                                topPadding: 4
                                bottomPadding: 4
                                onClicked: {
                                    if (modelData === "ollama") {
                                        KeyStore.setKey("ollama", "enabled")
                                    } else if (keyInput.text !== "") {
                                        KeyStore.setKey(modelData, keyInput.text)
                                        keyInput.text = ""
                                    }
                                }
                                background: StyledRect {
                                    variant: saveButton.down ? "overprimary" : (saveButton.hovered ? "primaryfocus" : "primary")
                                    radius: Styling.radius(4)
                                }
                                contentItem: Item {
                                    implicitWidth: saveButtonLabel.implicitWidth + saveButton.leftPadding + saveButton.rightPadding
                                    implicitHeight: saveButtonLabel.implicitHeight + saveButton.topPadding + saveButton.bottomPadding

                                    Text {
                                        id: saveButtonLabel
                                        text: saveButton.text
                                        color: Colors.overPrimary
                                        font.family: Config.theme.font
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        anchors.fill: parent
                                        anchors.leftMargin: saveButton.leftPadding
                                        anchors.rightMargin: saveButton.rightPadding
                                        anchors.topMargin: saveButton.topPadding
                                        anchors.bottomMargin: saveButton.bottomPadding
                                    }
                                }
                            }
                            Button {
                                id: clearButton
                                visible: KeyStore.hasKey(modelData)
                                text: modelData === "ollama" ? "Disable" : "Clear"
                                leftPadding: 6
                                rightPadding: 6
                                topPadding: 4
                                bottomPadding: 4
                                onClicked: KeyStore.deleteKey(modelData)
                                background: StyledRect {
                                    variant: "error"
                                    radius: Styling.radius(4)
                                }
                                contentItem: Item {
                                    implicitWidth: clearButtonLabel.implicitWidth + clearButton.leftPadding + clearButton.rightPadding
                                    implicitHeight: clearButtonLabel.implicitHeight + clearButton.topPadding + clearButton.bottomPadding

                                    Text {
                                        id: clearButtonLabel
                                        text: clearButton.text
                                        color: Colors.overError
                                        font.family: Config.theme.font
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        anchors.fill: parent
                                        anchors.leftMargin: clearButton.leftPadding
                                        anchors.rightMargin: clearButton.rightPadding
                                        anchors.topMargin: clearButton.topPadding
                                        anchors.bottomMargin: clearButton.bottomPadding
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            // Custom Provider
            Text {
                text: "Custom Provider"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(6)
                font.weight: Font.Bold
                color: Colors.overSurface
                Layout.fillWidth: true
                Layout.topMargin: 16
                Layout.bottomMargin: 8
            }
            
            StyledRect {
                Layout.fillWidth: true
                variant: "surface"
                radius: Styling.radius(8)
                implicitHeight: customCol.implicitHeight + 32

                ColumnLayout {
                    id: customCol
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "Custom Provider API Key"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(0)
                            font.weight: Font.Bold
                            color: Colors.overSurface
                            Layout.fillWidth: true
                        }
                        Text {
                            text: KeyStore.hasKey("custom") ? "Key Configured" : "Not Configured"
                            font.family: Config.theme.font
                            font.pixelSize: Styling.fontSize(-2)
                            color: KeyStore.hasKey("custom") ? Colors.success : Colors.outline
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12

                        TextField {
                            id: customKeyInput
                            Layout.fillWidth: true
                            placeholderText: "Enter API Key..."
                            echoMode: TextInput.Password
                            font.family: Config.theme.font
                            color: Colors.overSurface
                            padding: 6
                            
                            background: StyledRect {
                                variant: "internalbg"
                                radius: Styling.radius(4)
                                border.width: customKeyInput.activeFocus ? 2 : 0
                                border.color: Styling.srItem("primary")
                                anchors.fill: parent
                                anchors.leftMargin: -parent.padding
                                anchors.rightMargin: -parent.padding
                                anchors.topMargin: -parent.padding
                                anchors.bottomMargin: -parent.padding
                            }
                        }
                        Button {
                            id: customSaveButton
                            text: "Save"
                            hoverEnabled: true
                            leftPadding: 6
                            rightPadding: 6
                            topPadding: 4
                            bottomPadding: 4
                            onClicked: {
                                if (customKeyInput.text !== "") {
                                    KeyStore.setKey("custom", customKeyInput.text)
                                    customKeyInput.text = ""
                                }
                            }
                            background: StyledRect {
                                variant: customSaveButton.down ? "overprimary" : (customSaveButton.hovered ? "primaryfocus" : "primary")
                                radius: Styling.radius(4)
                            }
                            contentItem: Item {
                                implicitWidth: customSaveButtonLabel.implicitWidth + customSaveButton.leftPadding + customSaveButton.rightPadding
                                implicitHeight: customSaveButtonLabel.implicitHeight + customSaveButton.topPadding + customSaveButton.bottomPadding

                                Text {
                                    id: customSaveButtonLabel
                                    text: customSaveButton.text
                                    color: Colors.overPrimary
                                    font.family: Config.theme.font
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    anchors.fill: parent
                                    anchors.leftMargin: customSaveButton.leftPadding
                                    anchors.rightMargin: customSaveButton.rightPadding
                                    anchors.topMargin: customSaveButton.topPadding
                                    anchors.bottomMargin: customSaveButton.bottomPadding
                                }
                            }
                        }
                        Button {
                            id: customClearButton
                            visible: KeyStore.hasKey("custom")
                            text: "Clear"
                            leftPadding: 6
                            rightPadding: 6
                            topPadding: 4
                            bottomPadding: 4
                            onClicked: KeyStore.deleteKey("custom")
                            background: StyledRect {
                                variant: "error"
                                radius: Styling.radius(4)
                            }
                            contentItem: Item {
                                implicitWidth: customClearButtonLabel.implicitWidth + customClearButton.leftPadding + customClearButton.rightPadding
                                implicitHeight: customClearButtonLabel.implicitHeight + customClearButton.topPadding + customClearButton.bottomPadding

                                Text {
                                    id: customClearButtonLabel
                                    text: customClearButton.text
                                    color: Colors.overError
                                    font.family: Config.theme.font
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    anchors.fill: parent
                                    anchors.leftMargin: customClearButton.leftPadding
                                    anchors.rightMargin: customClearButton.rightPadding
                                    anchors.topMargin: customClearButton.topPadding
                                    anchors.bottomMargin: customClearButton.bottomPadding
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Colors.outline
                        opacity: 0.2
                        Layout.topMargin: 8
                        Layout.bottomMargin: 8
                    }

                    Text {
                        text: "Custom Endpoint"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(0)
                        color: Colors.overSurface
                    }
                    
                    TextField {
                        id: endpointInput
                        Layout.fillWidth: true
                        text: Config.ai.customEndpoint !== undefined ? Config.ai.customEndpoint : ""
                        placeholderText: "e.g. https://api.example.com/v1/chat/completions"
                        font.family: Config.theme.font
                        color: Colors.overSurface
                        padding: 6
                        
                        onTextChanged: {
                            if (Config.ai.customEndpoint !== undefined) {
                                Config.ai.customEndpoint = text;
                            }
                        }
                        
                        background: StyledRect {
                            variant: "internalbg"
                            radius: Styling.radius(4)
                            border.width: endpointInput.activeFocus ? 2 : 0
                            border.color: Styling.srItem("primary")
                            anchors.fill: parent
                            anchors.leftMargin: -parent.padding
                            anchors.rightMargin: -parent.padding
                            anchors.topMargin: -parent.padding
                            anchors.bottomMargin: -parent.padding
                        }
                    }

                    Text {
                        text: "Custom cURL Template"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(0)
                        color: Colors.overSurface
                        Layout.topMargin: 8
                    }
                    
                    Text {
                        text: "Placeholders: {{ENDPOINT}}, {{API_KEY}}, {{BODY_PATH}}"
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.outline
                    }
                    
                    TextField {
                        id: curlInput
                        Layout.fillWidth: true
                        text: Config.ai.customCurlTemplate !== undefined ? Config.ai.customCurlTemplate : ""
                        placeholderText: "curl -X POST {{ENDPOINT}} -H 'Authorization: Bearer {{API_KEY}}' -d @{{BODY_PATH}}"
                        font.family: Config.theme.monoFont
                        color: Colors.overSurface
                        padding: 6
                        
                        onTextChanged: {
                            if (Config.ai.customCurlTemplate !== undefined) {
                                Config.ai.customCurlTemplate = text;
                            }
                        }
                        
                        background: StyledRect {
                            variant: "internalbg"
                            radius: Styling.radius(4)
                            border.width: curlInput.activeFocus ? 2 : 0
                            border.color: Styling.srItem("primary")
                            anchors.fill: parent
                            anchors.leftMargin: -parent.padding
                            anchors.rightMargin: -parent.padding
                            anchors.topMargin: -parent.padding
                            anchors.bottomMargin: -parent.padding
                        }
                    }
                }
            }
        }
    }
}
