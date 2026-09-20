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

    readonly property var chatProviders: [
        { id: "openai", title: "OpenAI" },
        { id: "anthropic", title: "Anthropic" },
        { id: "gemini", title: "Gemini" },
        { id: "openrouter", title: "OpenRouter" },
        { id: "ollama", title: "Ollama" }
    ]

    function persistAi() {
        Config.saveAi();
    }

    component ProviderModels: ColumnLayout {
        id: picker
        required property string providerId
        property string filterText: ""

        readonly property var allModels: {
            Ai.models;
            KeyStore.revision;
            Config.ai.manualModelsJson;
            Config.ai.customModelsJson;
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
                const hay = [m.name, Ai.modelIdOf(m), m.description].map(x => String(x || "")).join(" ");
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
        readonly property bool ignoreCatalog: {
            Config.ai.ignoreModelCatalog;
            return Config.ignoresModelCatalog(picker.providerId);
        }
        readonly property var manuals: {
            Config.ai.manualModelsJson;
            Config.ai.customModelsJson;
            Config.ai.customModels;
            return Config.readManualModels(picker.providerId);
        }
        readonly property bool showPicker: {
            Config.ai.customModels;
            Config.ai.customModelsJson;
            Config.ai.manualModelsJson;
            if (picker.hasKey)
                return true;
            return picker.manuals.length > 0 || picker.ignoreCatalog;
        }

        function itemLabel(item) {
            if (!item)
                return "";
            return item.name || Ai.modelIdOf(item);
        }

        function isSelected(item) {
            if (!item)
                return false;
            const mid = Ai.modelIdOf(item);
            const provider = String(item.provider || picker.providerId || "").toLowerCase();
            if (provider !== picker.providerId)
                return false;
            if (picker.selectedId && mid && picker.selectedId === mid)
                return true;
            return Ai.isSameModel(Ai.currentModel, item);
        }

        function addManual(displayName, modelId) {
            const mid = String(modelId || "").trim();
            if (!mid)
                return;
            const display = String(displayName || "").trim();
            const next = Config.readManualModels(picker.providerId);
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
            Config.writeManualModels(picker.providerId, next);
            Ai.fetchAvailableModels();
        }

        function removeManual(index) {
            const next = Config.readManualModels(picker.providerId);
            next.splice(index, 1);
            Config.writeManualModels(picker.providerId, next);
            Ai.fetchAvailableModels();
        }

        Layout.fillWidth: true
        spacing: 8

        SettingsRow {
            label: qsTr("Ignore catalog")
            description: qsTr("Skip the provider model list and use only IDs you add")
            SettingsSwitch {
                checked: picker.ignoreCatalog
                onToggled: value => {
                    Config.setIgnoreModelCatalog(picker.providerId, value);
                    Ai.fetchAvailableModels();
                }
            }
        }

        SettingsRow {
            label: qsTr("Manual model IDs")
            description: picker.ignoreCatalog ? qsTr("Only these IDs are listed") : qsTr("Extra IDs if the catalog is missing or you want less clutter")
            stacked: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Repeater {
                    model: picker.manuals
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
                            onClicked: picker.removeManual(index)
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    SettingsField {
                        id: newManualName
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        placeholder: qsTr("Display name")
                        onAccepted: {
                            picker.addManual(newManualName.text, newManualId.text);
                            newManualName.text = "";
                            newManualId.text = "";
                        }
                    }

                    SettingsField {
                        id: newManualId
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        placeholder: qsTr("Model ID")
                        onAccepted: {
                            picker.addManual(newManualName.text, newManualId.text);
                            newManualName.text = "";
                            newManualId.text = "";
                        }
                    }

                    SettingsButton {
                        text: qsTr("Add")
                        enabled: newManualId.text.trim() !== ""
                        onClicked: {
                            picker.addManual(newManualName.text, newManualId.text);
                            newManualName.text = "";
                            newManualId.text = "";
                        }
                    }
                }
            }
        }

        SettingsRow {
            visible: picker.showPicker
            label: qsTr("Default model")
            description: {
                if (Ai.fetchingModels)
                    return qsTr("Refreshing model list…");
                const n = picker.allModels.length;
                if (n === 0)
                    return picker.ignoreCatalog ? qsTr("No manual IDs yet") : qsTr("No models yet — refresh after the key is saved");
                if (picker.selectedId) {
                    let label = picker.selectedId;
                    for (let i = 0; i < picker.allModels.length; i++) {
                        if (Ai.modelIdOf(picker.allModels[i]) === picker.selectedId) {
                            label = picker.itemLabel(picker.allModels[i]);
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
                            readonly property bool selected: picker.isSelected(item)
                            Layout.fillWidth: true
                            text: (selected ? "● " : "○ ") + picker.itemLabel(item)
                            kind: selected ? "primary" : "common"
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

    component ComputerUseModelPicker: ColumnLayout {
        id: cuPicker
        property string filterText: ""

        readonly property var allModels: {
            Ai.models;
            KeyStore.revision;
            Config.ai.manualModelsJson;
            Config.ai.customModelsJson;
            return Ai.models;
        }
        readonly property var filteredModels: {
            const q = String(cuPicker.filterText || "").trim().toLowerCase();
            const all = cuPicker.allModels || [];
            if (!q)
                return all;
            const out = [];
            for (let i = 0; i < all.length; i++) {
                const m = all[i];
                const hay = [m.name, Ai.modelIdOf(m), m.provider, m.description].map(x => String(x || "")).join(" ");
                if (hay.toLowerCase().indexOf(q) >= 0)
                    out.push(m);
            }
            return out;
        }
        readonly property string selectedId: {
            Config.ai.computerUseModel;
            return String(Config.ai.computerUseModel || "").trim();
        }
        readonly property bool usingSpotlight: cuPicker.selectedId === ""

        function itemLabel(item) {
            if (!item)
                return "";
            const name = item.name || Ai.modelIdOf(item);
            const provider = String(item.provider || "").trim();
            if (provider && name)
                return name + " · " + provider;
            return name;
        }

        function isSelected(item) {
            if (!item || !cuPicker.selectedId)
                return false;
            return Ai.modelIdOf(item) === cuPicker.selectedId;
        }

        function choose(item) {
            const mid = item ? Ai.modelIdOf(item) : "";
            if (!mid)
                return;
            Config.ai.computerUseModel = mid;
            root.persistAi();
        }

        function clearOverride() {
            Config.ai.computerUseModel = "";
            root.persistAi();
        }

        Layout.fillWidth: true
        spacing: 8

        SettingsRow {
            label: qsTr("Computer use model")
            description: {
                if (Ai.fetchingModels)
                    return qsTr("Refreshing model list…");
                if (cuPicker.usingSpotlight)
                    return qsTr("Same as the Spotlight/chat model. Pick one below to use a different model for computer use only.");
                let label = cuPicker.selectedId;
                const all = cuPicker.allModels || [];
                for (let i = 0; i < all.length; i++) {
                    if (Ai.modelIdOf(all[i]) === cuPicker.selectedId) {
                        label = cuPicker.itemLabel(all[i]);
                        break;
                    }
                }
                return qsTr("Computer use uses %1. Spotlight/chat is unchanged.").arg(label);
            }
            stacked: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                SettingsButton {
                    Layout.fillWidth: true
                    text: (cuPicker.usingSpotlight ? "● " : "○ ") + qsTr("Same as Spotlight")
                    kind: cuPicker.usingSpotlight ? "primary" : "common"
                    onClicked: cuPicker.clearOverride()
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    SettingsField {
                        Layout.fillWidth: true
                        placeholder: (cuPicker.allModels || []).length > 8 ? qsTr("Search models…") : qsTr("Filter…")
                        onTextChanged: cuPicker.filterText = text
                        onAccepted: cuPicker.filterText = text
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
                    visible: cuPicker.filteredModels.length > 0

                    Repeater {
                        model: Math.min(cuPicker.filteredModels.length, 10)
                        delegate: SettingsButton {
                            required property int index
                            readonly property var item: cuPicker.filteredModels[index]
                            readonly property bool selected: cuPicker.isSelected(item)
                            Layout.fillWidth: true
                            text: (selected ? "● " : "○ ") + cuPicker.itemLabel(item)
                            kind: selected ? "primary" : "common"
                            onClicked: cuPicker.choose(item)
                        }
                    }

                    Text {
                        visible: cuPicker.filteredModels.length > 10
                        Layout.fillWidth: true
                        text: qsTr("Showing 10 of %1 — refine the search").arg(cuPicker.filteredModels.length)
                        font.family: Config.theme.font
                        font.pixelSize: Styling.fontSize(-2)
                        color: Colors.overSurfaceVariant
                        wrapMode: Text.Wrap
                    }
                }

                Text {
                    visible: cuPicker.filteredModels.length === 0
                    Layout.fillWidth: true
                    text: qsTr("No models yet — add a provider key or refresh")
                    font.family: Config.theme.font
                    font.pixelSize: Styling.fontSize(-2)
                    color: Colors.overSurfaceVariant
                    wrapMode: Text.Wrap
                }
            }
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
                Layout.fillWidth: true
                Layout.preferredWidth: 0
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
                        onEditingFinished: {
                            Config.ai.workspace = text;
                            root.persistAi();
                        }
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
                            root.persistAi();
                        }
                    }
                }

                SettingsRow {
                    label: "Position"
                    description: "Where the bar sits; bottom grows the transcript up"
                    stacked: true
                    SegmentedSwitch {
                        currentValue: Config.ai.overlayAnchor || "top"
                        model: [
                            { value: "top", label: qsTr("Top") },
                            { value: "center", label: qsTr("Center") },
                            { value: "bottom", label: qsTr("Bottom") }
                        ]
                        onActivated: value => {
                            Config.ai.overlayAnchor = value;
                            root.persistAi();
                        }
                    }
                }

                SettingsRow {
                    label: "Offset X"
                    SettingsSpinBox {
                        from: -400
                        to: 400
                        stepSize: 4
                        suffix: "px"
                        value: Config.ai.overlayOffsetX || 0
                        onValueEdited: newValue => {
                            Config.ai.overlayOffsetX = newValue;
                            root.persistAi();
                        }
                    }
                }

                SettingsRow {
                    label: "Offset Y"
                    SettingsSpinBox {
                        from: -400
                        to: 400
                        stepSize: 4
                        suffix: "px"
                        value: Config.ai.overlayOffsetY || 0
                        onValueEdited: newValue => {
                            Config.ai.overlayOffsetY = newValue;
                            root.persistAi();
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
                            root.persistAi();
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
                        root.persistAi();
                    }
                }
                PolicyRow {
                    label: "Apply diffs"
                    currentValue: Config.ai.executionProfile.applyCodeDiffs
                    onActivated: value => {
                        Config.ai.executionProfile.applyCodeDiffs = value;
                        root.persistAi();
                    }
                }
                PolicyRow {
                    label: "Shell commands"
                    currentValue: Config.ai.executionProfile.executeCommands
                    onActivated: value => {
                        Config.ai.executionProfile.executeCommands = value;
                        root.persistAi();
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
                        root.persistAi();
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
                        root.persistAi();
                    }
                }

                ComputerUseModelPicker {}

                SettingsRow {
                    label: "Web search"
                    description: "Let the agent search the web with Exa"
                    SettingsSwitch {
                        checked: Config.ai.executionProfile.webSearchEnabled ?? true
                        onToggled: value => {
                            Config.ai.executionProfile.webSearchEnabled = value;
                            root.persistAi();
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
                        onEditingFinished: {
                            Config.ai.executionProfile.commandAllowlist = text.split("\n").map(s => s.trim()).filter(s => s.length);
                            root.persistAi();
                        }
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
                        onEditingFinished: {
                            Config.ai.executionProfile.commandDenylist = text.split("\n").map(s => s.trim()).filter(s => s.length);
                            root.persistAi();
                        }
                    }
                }
            }

            SettingsGroup {
                title: "Jev"
                description: "Optional TypeSafe judgments for routing, window focus, and extra computer-use review. Off sends nothing. Shadow scores privately. Active may take high-confidence native shortcuts; it never weakens permissions."

                SettingsRow {
                    label: "Mode"
                    description: "Installing Ambxst[+] leaves this off"
                    stacked: true
                    SegmentedSwitch {
                        currentValue: (Config.ai.jev && Config.ai.jev.mode) ? Config.ai.jev.mode : "off"
                        model: [
                            { value: "off", label: qsTr("Off") },
                            { value: "shadow", label: qsTr("Shadow") },
                            { value: "active", label: qsTr("Active") }
                        ]
                        onActivated: value => {
                            if (Config.ai.jev)
                                Config.ai.jev.mode = value;
                            root.persistAi();
                        }
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
                                root.persistAi();
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
                                Config.setContextProvider(modelData.key, value);
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
                                root.persistAi();
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
                            root.persistAi();
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

                SettingsRow {
                    label: "TypeSafe"
                    description: "Jev API key for optional desktop judgments"
                    stacked: true
                    KeyEntry {
                        providerId: "typesafe"
                    }
                }
            }
        }
    }
}
