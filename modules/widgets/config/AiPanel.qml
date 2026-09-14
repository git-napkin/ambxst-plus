import QtQuick
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

    readonly property var decideModel: [
        { value: "AgentDecides", label: "Agent decides" },
        { value: "AlwaysAllow", label: "Always allow" },
        { value: "AlwaysAsk", label: "Always ask" }
    ]

    readonly property string currentProvider: (Ai.currentModel && Ai.currentModel.provider) ? String(Ai.currentModel.provider).toLowerCase() : ""
    readonly property bool showSampling: currentProvider === "ollama" || currentProvider === "custom"

    readonly property var chatProviders: [
        { id: "openai", title: "OpenAI" },
        { id: "anthropic", title: "Anthropic" },
        { id: "gemini", title: "Gemini" },
        { id: "openrouter", title: "OpenRouter" },
        { id: "ollama", title: "Ollama" }
    ]

    function addCustomModel() {
        const mid = newCustomModelId.text.trim();
        if (!mid)
            return;
        const display = newCustomModelName.text.trim();
        const next = Config.readCustomModels();
        let updated = false;
        for (let i = 0; i < next.length; i++) {
            if (String(next[i].model || "") === mid) {
                next[i] = {
                    model: mid,
                    name: display || next[i].name || mid
                };
                updated = true;
                break;
            }
        }
        if (!updated)
            next.push({
                model: mid,
                name: display || mid
            });
        Config.writeCustomModels(next);
        newCustomModelId.text = "";
        newCustomModelName.text = "";
    }

    readonly property var customModelList: {
        Config.ai.customModelsJson;
        Config.ai.customModels;
        return Config.readCustomModels();
    }

    component ProviderModels: ColumnLayout {
        id: picker
        required property string providerId
        property string filterText: ""

        readonly property var allModels: {
            Ai.models;
            KeyStore.revision;
            return Ai.modelsFor(picker.providerId);
        }
        readonly property var filteredModels: {
            const q = String(picker.filterText || "").trim().toLowerCase();
            const all = picker.allModels || [];
            if (!q)
                return all;
            const out = [];
            for (let i = 0; i < all.length; i++) {
                const m = all[i];
                const hay = [m.name, m.model, m.description].map(x => String(x || "")).join(" ");
                if (hay.toLowerCase().indexOf(q) >= 0)
                    out.push(m);
            }
            return out;
        }
        readonly property string selectedId: {
            Config.ai.defaultModels;
            Config.ai.defaultModel;
            Ai.currentModel;
            return Ai.providerDefault(picker.providerId);
        }
        readonly property bool hasKey: {
            KeyStore.revision;
            return KeyStore.hasKey(picker.providerId);
        }
        readonly property bool showPicker: {
            Config.ai.customModels;
            Config.ai.customModelsJson;
            if (picker.hasKey)
                return true;
            if (picker.providerId === "custom")
                return Config.readCustomModels().length > 0;
            return false;
        }

        Layout.fillWidth: true
        spacing: 8
        visible: picker.showPicker

        SettingsRow {
            label: qsTr("Default model")
            description: {
                if (Ai.fetchingModels)
                    return qsTr("Refreshing model list…");
                const n = picker.allModels.length;
                if (n === 0)
                    return qsTr("No models yet — refresh after the key is saved");
                if (picker.selectedId) {
                    let label = picker.selectedId;
                    for (let i = 0; i < picker.allModels.length; i++) {
                        if (picker.allModels[i].model === picker.selectedId) {
                            label = picker.allModels[i].name || picker.selectedId;
                            break;
                        }
                    }
                    return qsTr("Selected") + ": " + label + " · " + n + " " + qsTr("available");
                }
                return n + " " + qsTr("available — pick one to use");
            }
            stacked: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    SettingsField {
                        id: modelSearch
                        Layout.fillWidth: true
                        placeholder: picker.allModels.length > 8 ? qsTr("Search models…") : qsTr("Filter…")
                        onTextChanged: picker.filterText = text
                        onAccepted: picker.filterText = text
                    }

                    SettingsButton {
                        text: qsTr("Refresh")
                        enabled: !Ai.fetchingModels
                        onClicked: Ai.fetchAvailableModels()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    visible: picker.filteredModels.length > 0

                    Repeater {
                        model: Math.min(picker.filteredModels.length, 10)
                        delegate: SettingsButton {
                            required property int index
                            readonly property var item: picker.filteredModels[index]
                            Layout.fillWidth: true
                            text: {
                                const m = item;
                                if (!m)
                                    return "";
                                const active = picker.selectedId === m.model
                                    || (Ai.currentModel && Ai.currentModel.model === m.model
                                        && String(Ai.currentModel.provider).toLowerCase() === picker.providerId);
                                return (active ? "● " : "○ ") + (m.name || m.model);
                            }
                            kind: {
                                const m = item;
                                if (!m)
                                    return "common";
                                if (picker.selectedId === m.model)
                                    return "primary";
                                return "common";
                            }
                            onClicked: {
                                if (item)
                                    Ai.setProviderDefault(picker.providerId, item);
                            }
                        }
                    }

                    Text {
                        visible: picker.filteredModels.length > 10
                        Layout.fillWidth: true
                        text: qsTr("Showing 10 of %1 — refine the search").arg(picker.filteredModels.length)
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.overSurfaceVariant
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }

    component PolicyRow: SettingsRow {
        id: policyRow
        property var currentValue
        property var options: root.decideModel
        stacked: true
        signal activated(var value)

        SegmentedSwitch {
            currentValue: policyRow.currentValue
            model: policyRow.options
            onActivated: value => policyRow.activated(value)
        }
    }

    component ValueSlider: Item {
        id: sliderRoot
        property alias value: slider.value
        property alias tooltipText: slider.tooltipText
        signal moved(real value)

        implicitHeight: 28
        implicitWidth: 180
        Layout.fillWidth: true
        Layout.preferredHeight: 28

        StyledSlider {
            id: slider
            anchors.fill: parent
            resizeParent: false
            onValueChanged: sliderRoot.moved(value)
        }
    }

    component KeyEntry: ColumnLayout {
        id: entry
        required property string providerId
        property bool toggleMode: false
        property string fieldPlaceholder: qsTr("Enter API key")

        readonly property var savedKeys: {
            KeyStore.revision;
            return KeyStore.keysFor(entry.providerId);
        }
        readonly property bool saved: savedKeys.length > 0
        property bool pendingSave: false
        property string saveError: ""

        Layout.fillWidth: true
        spacing: 8

        Repeater {
            model: entry.savedKeys.length
            delegate: RowLayout {
                id: savedRow
                required property int index
                readonly property var item: entry.savedKeys[savedRow.index] || {}
                Layout.fillWidth: true
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    text: {
                        const item = savedRow.item;
                        const mask = entry.maskKey(item.api_key);
                        const label = String(item.label || "").trim();
                        if (entry.toggleMode)
                            return qsTr("Enabled");
                        if (label)
                            return label + " · " + mask;
                        return qsTr("Saved") + " · " + mask;
                    }
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-1)
                    color: Colors.overBackground
                    elide: Text.ElideRight
                }

                SettingsButton {
                    text: entry.toggleMode ? qsTr("Disable") : qsTr("Remove")
                    kind: "error"
                    onClicked: KeyStore.deleteKeyById(savedRow.item.id)
                }
            }
        }

        RowLayout {
            visible: !entry.toggleMode
            Layout.fillWidth: true
            spacing: 8

            SettingsField {
                id: labelField
                visible: !entry.toggleMode
                Layout.preferredWidth: 120
                Layout.fillWidth: false
                placeholder: qsTr("Label")
                onAccepted: entry.save()
            }

            SettingsField {
                id: keyField
                Layout.fillWidth: true
                password: true
                placeholder: entry.saved ? qsTr("Add another key") : entry.fieldPlaceholder
                onAccepted: entry.save()
            }

            SettingsButton {
                text: entry.saved ? qsTr("Add") : qsTr("Save")
                enabled: keyField.text.trim() !== ""
                onClicked: entry.save()
            }
        }

        Text {
            visible: entry.saveError !== ""
            Layout.fillWidth: true
            text: entry.saveError
            font.family: Config.theme.font
            font.pixelSize: Styling.fontSize(-2)
            color: Colors.error
            wrapMode: Text.Wrap
        }

        RowLayout {
            visible: entry.toggleMode && !entry.saved
            Layout.fillWidth: true
            spacing: 8

            SettingsButton {
                text: qsTr("Enable")
                kind: "primary"
                onClicked: KeyStore.setKey(entry.providerId, "enabled")
            }
        }

        function maskKey(key) {
            const value = String(key || "");
            if (!value || value === "enabled")
                return qsTr("Saved");
            if (value.length <= 4)
                return "••••";
            return "•••• " + value.slice(-4);
        }

        function save() {
            const value = keyField.text.trim();
            if (!value)
                return;
            entry.saveError = "";
            entry.pendingSave = true;
            KeyStore.addKey(entry.providerId, value, labelField.text.trim());
        }

        Connections {
            target: KeyStore
            function onSaveFinished(ok, message) {
                if (!entry.pendingSave)
                    return;
                entry.pendingSave = false;
                if (ok) {
                    keyField.text = "";
                    labelField.text = "";
                    entry.saveError = "";
                    return;
                }
                const raw = String(message || "");
                if (raw.indexOf("cryptography") >= 0 || raw.indexOf("No module named") >= 0)
                    entry.saveError = qsTr("Couldn't save the key (missing cryptography).");
                else
                    entry.saveError = qsTr("Couldn't save the key.");
            }
        }
    }

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
            spacing: 20

            Text {
                text: "AI"
                font.family: Config.theme.font
                font.pixelSize: Styling.fontSize(10)
                font.weight: Font.Bold
                color: Colors.overBackground
                Layout.fillWidth: true
            }

            SettingsGroup {
                title: "Overlay"
                description: "Spotlight chat size, placement, and the project the agent works in."

                SettingsRow {
                    label: "Workspace"
                    description: "Folder the agent reads and edits"
                    stacked: true
                    SettingsField {
                        value: Config.ai.workspace || ""
                        placeholder: Quickshell.env("HOME") || qsTr("Project folder")
                        onEditingFinished: Config.ai.workspace = text
                    }
                }

                SettingsRow {
                    label: "System prompt"
                    description: "Standing instructions for the assistant"
                    stacked: true
                    SettingsField {
                        multiline: true
                        areaHeight: 120
                        value: Config.ai.systemPrompt || ""
                        placeholder: qsTr("You are a helpful assistant…")
                        onEditingFinished: Config.ai.systemPrompt = text
                    }
                }

                SettingsRow {
                    label: "Width"
                    SettingsSpinBox {
                        from: 400
                        to: 1200
                        stepSize: 20
                        value: Config.ai.overlayWidth || 640
                        onValueEdited: newValue => {
                            Config.ai.overlayWidth = newValue;
                        }
                    }
                }

                SettingsRow {
                    label: "Vertical position"
                    stacked: true
                    ValueSlider {
                        value: ((Config.ai.overlayYFraction ?? 0.22) - 0.05) / 0.45
                        tooltipText: Math.round((0.05 + value * 0.45) * 100) + "%"
                        onMoved: next => {
                            const mapped = 0.05 + next * 0.45;
                            if (Math.abs((Config.ai.overlayYFraction ?? 0.22) - mapped) > 0.001)
                                Config.ai.overlayYFraction = mapped;
                        }
                    }
                }

                SettingsRow {
                    label: "Show scrim"
                    description: "Dim the desktop behind the overlay"
                    SettingsSwitch {
                        checked: Config.ai.showScrim ?? true
                        onToggled: value => {
                            Config.ai.showScrim = value;
                        }
                    }
                }

                SettingsRow {
                    visible: root.showSampling
                    label: "Temperature"
                    description: "Only used for Ollama and custom endpoints"
                    stacked: true
                    ValueSlider {
                        value: (Config.ai.temperature ?? 0.7) / 2
                        tooltipText: ((Config.ai.temperature ?? 0.7)).toFixed(1)
                        onMoved: next => {
                            const mapped = next * 2;
                            if (Math.abs((Config.ai.temperature ?? 0.7) - mapped) > 0.01)
                                Config.ai.temperature = mapped;
                        }
                    }
                }

                SettingsRow {
                    visible: root.showSampling
                    label: "Max tokens"
                    description: "Only used for Ollama and custom endpoints"
                    SettingsSpinBox {
                        from: 256
                        to: 128000
                        stepSize: 256
                        value: Config.ai.maxTokens || 4096
                        onValueEdited: newValue => {
                            Config.ai.maxTokens = newValue;
                        }
                    }
                }
            }

            SettingsGroup {
                title: "Execution profile"
                description: "What the agent may do on its own, and when it should ask first."

                PolicyRow {
                    label: "Read files"
                    currentValue: Config.ai.executionProfile.readFiles
                    onActivated: value => {
                        Config.ai.executionProfile.readFiles = value;
                    }
                }
                PolicyRow {
                    label: "Apply diffs"
                    currentValue: Config.ai.executionProfile.applyCodeDiffs
                    onActivated: value => {
                        Config.ai.executionProfile.applyCodeDiffs = value;
                    }
                }
                PolicyRow {
                    label: "Shell commands"
                    currentValue: Config.ai.executionProfile.executeCommands
                    onActivated: value => {
                        Config.ai.executionProfile.executeCommands = value;
                    }
                }
                PolicyRow {
                    label: "Ask questions"
                    currentValue: Config.ai.executionProfile.askUserQuestion
                    options: [
                        { value: "AlwaysAsk", label: "Always ask" },
                        { value: "AskExceptInAutoApprove", label: "Skip if auto" },
                        { value: "Never", label: "Never" }
                    ]
                    onActivated: value => {
                        Config.ai.executionProfile.askUserQuestion = value;
                    }
                }
                PolicyRow {
                    label: "Computer use"
                    description: "See and control the desktop. Default is Never. Always ask shows a summary before the first session."
                    currentValue: Config.ai.executionProfile.computerUse
                    options: [
                        { value: "Never", label: "Never" },
                        { value: "AlwaysAsk", label: "Always ask" },
                        { value: "AlwaysAllow", label: "Always allow" }
                    ]
                    onActivated: value => {
                        Config.ai.executionProfile.computerUse = value;
                    }
                }

                SettingsRow {
                    label: "Web search"
                    description: "Let the agent search the web with Exa"
                    SettingsSwitch {
                        checked: Config.ai.executionProfile.webSearchEnabled ?? true
                        onToggled: value => {
                            Config.ai.executionProfile.webSearchEnabled = value;
                        }
                    }
                }

                SettingsRow {
                    label: "Command allowlist"
                    description: "One regex per line"
                    stacked: true
                    SettingsField {
                        multiline: true
                        areaHeight: 80
                        mono: true
                        value: (Config.ai.executionProfile.commandAllowlist || []).join("\n")
                        placeholder: qsTr("^ls\\b")
                        onEditingFinished: Config.ai.executionProfile.commandAllowlist = text.split("\n").map(s => s.trim()).filter(s => s.length)
                    }
                }

                SettingsRow {
                    label: "Command denylist"
                    description: "One regex per line"
                    stacked: true
                    SettingsField {
                        multiline: true
                        areaHeight: 80
                        mono: true
                        value: (Config.ai.executionProfile.commandDenylist || []).join("\n")
                        placeholder: qsTr("rm\\s+-rf")
                        onEditingFinished: Config.ai.executionProfile.commandDenylist = text.split("\n").map(s => s.trim()).filter(s => s.length)
                    }
                }
            }

            SettingsGroup {
                title: "Enabled tools"
                description: "Tools the agent can call during a session."

                Repeater {
                    model: [
                        { id: "read_files", label: "Read files" },
                        { id: "grep", label: "Search in files" },
                        { id: "file_glob", label: "Find files" },
                        { id: "apply_file_diffs", label: "Apply diffs" },
                        { id: "run_shell_command", label: "Shell commands" },
                        { id: "ask_user_question", label: "Ask questions" },
                        { id: "read_skill", label: "Skills" },
                        { id: "exa_search", label: "Web search" },
                        { id: "exa_contents", label: "Read pages" },
                        { id: "native", label: "Desktop actions" }
                    ]
                    delegate: SettingsRow {
                        required property var modelData
                        label: modelData.label
                        SettingsSwitch {
                            checked: (Config.ai.enabledTools || []).indexOf(modelData.id) !== -1
                            onToggled: value => {
                                const cur = (Config.ai.enabledTools || []).slice();
                                const i = cur.indexOf(modelData.id);
                                if (value && i === -1)
                                    cur.push(modelData.id);
                                if (!value && i !== -1)
                                    cur.splice(i, 1);
                                Config.ai.enabledTools = cur;
                            }
                        }
                    }
                }
            }

            SettingsGroup {
                title: "Context"
                description: "Extra live shell state attached to each request."

                Repeater {
                    model: [
                        { key: "focusedWindow", label: "Focused window" },
                        { key: "clipboard", label: "Clipboard" },
                        { key: "notifications", label: "Notifications" },
                        { key: "weather", label: "Weather" },
                        { key: "resources", label: "Resources" }
                    ]
                    delegate: SettingsRow {
                        required property var modelData
                        label: modelData.label
                        SettingsSwitch {
                            checked: Config.ai.contextProviders[modelData.key] ?? false
                            onToggled: value => {
                                Config.ai.contextProviders[modelData.key] = value;
                            }
                        }
                    }
                }
            }

            SettingsGroup {
                title: "Saved commands"
                description: "Named prompts you can run from the overlay."

                Repeater {
                    model: Config.ai.commands || []
                    delegate: SettingsRow {
                        required property var modelData
                        required property int index
                        label: modelData.name || modelData.id || qsTr("Command")
                        description: modelData.prompt || ""
                        SettingsButton {
                            icon: Icons.trash
                            kind: "error"
                            implicitWidth: 36
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
                    spacing: 8
                    SettingsField {
                        id: newCmdName
                        Layout.fillWidth: true
                        placeholder: qsTr("Name")
                    }
                    SettingsField {
                        id: newCmdPrompt
                        Layout.fillWidth: true
                        placeholder: qsTr("Prompt")
                    }
                    SettingsButton {
                        text: qsTr("Add")
                        enabled: newCmdName.text.trim() !== "" && newCmdPrompt.text.trim() !== ""
                        onClicked: {
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
            }

            Repeater {
                model: root.chatProviders
                delegate: SettingsGroup {
                    required property var modelData
                    title: modelData.title

                    KeyEntry {
                        providerId: modelData.id
                        toggleMode: modelData.id === "ollama"
                    }

                    ProviderModels {
                        providerId: modelData.id
                    }
                }
            }

            SettingsGroup {
                title: (Config.ai.customName || "").trim() !== "" ? Config.ai.customName : "Custom"

                KeyEntry {
                    providerId: "custom"
                }

                SettingsRow {
                    label: "Display name"
                    description: "Optional label for this custom provider"
                    stacked: true
                    SettingsField {
                        value: Config.ai.customName || ""
                        placeholder: qsTr("My local LLM")
                        onEditingFinished: {
                            Config.ai.customName = text.trim();
                            Config.saveAi();
                        }
                    }
                }

                SettingsRow {
                    label: "Endpoint"
                    description: "OpenAI-compatible base URL ending in /v1"
                    stacked: true
                    SettingsField {
                        value: Config.ai.customEndpoint || ""
                        placeholder: "https://api.example.com/v1"
                        onEditingFinished: {
                            Config.ai.customEndpoint = text.trim();
                            Config.saveAi();
                        }
                    }
                }

                SettingsRow {
                    label: "Models"
                    description: "Manual model IDs when /v1/models is missing or incomplete"
                    stacked: true

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Repeater {
                            model: root.customModelList
                            delegate: RowLayout {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                spacing: 8

                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        const name = String(modelData.name || "").trim();
                                        const mid = String(modelData.model || modelData.id || "").trim();
                                        if (name && mid && name !== mid)
                                            return name + " · " + mid;
                                        return name || mid || qsTr("Model");
                                    }
                                    font.family: Config.theme.font
                                    font.pixelSize: Styling.fontSize(-1)
                                    color: Colors.overBackground
                                    elide: Text.ElideRight
                                }

                                SettingsButton {
                                    text: qsTr("Remove")
                                    kind: "error"
                                    onClicked: {
                                        const next = Config.readCustomModels();
                                        next.splice(index, 1);
                                        Config.writeCustomModels(next);
                                    }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            SettingsField {
                                id: newCustomModelName
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                placeholder: qsTr("Display name")
                                onAccepted: root.addCustomModel()
                            }

                            SettingsField {
                                id: newCustomModelId
                                Layout.fillWidth: true
                                Layout.preferredWidth: 1
                                placeholder: qsTr("Model ID")
                                onAccepted: root.addCustomModel()
                            }

                            SettingsButton {
                                text: qsTr("Add")
                                enabled: newCustomModelId.text.trim() !== ""
                                onClicked: root.addCustomModel()
                            }
                        }
                    }
                }

                ProviderModels {
                    providerId: "custom"
                }

                SettingsRow {
                    label: "cURL template"
                    description: "Placeholders: {{ENDPOINT}}, {{API_KEY}}, {{BODY_PATH}}"
                    stacked: true
                    SettingsField {
                        mono: true
                        value: Config.ai.customCurlTemplate || ""
                        placeholder: "curl -X POST {{ENDPOINT}}/chat/completions -H 'Authorization: Bearer {{API_KEY}}' -d @{{BODY_PATH}}"
                        onEditingFinished: {
                            Config.ai.customCurlTemplate = text;
                            Config.saveAi();
                        }
                    }
                }
            }

            SettingsGroup {
                title: "Misc keys"
                description: "Credentials for tools that are not chat providers."

                SettingsRow {
                    label: "Exa"
                    description: "Web search and page contents"
                    stacked: true
                    KeyEntry {
                        providerId: "exa"
                    }
                }
            }
        }
    }
}
