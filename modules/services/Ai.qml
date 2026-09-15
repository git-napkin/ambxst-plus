pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.config
import qs.modules.services
import "ai"

Singleton {
    id: root

    property string agentScript: Qt.resolvedUrl("../../scripts/ai/agent.py").toString().replace("file://", "")
    property string bundledSkills: Qt.resolvedUrl("../../assets/ai/skills").toString().replace("file://", "")

    property list<AiModel> models: []
    property AiModel currentModel: models.length > 0 ? models[0] : null
    property bool persistenceReady: false
    property string savedModelId: ""
    property bool isRestored: false
    property bool fetchingModels: false
    property bool agentReady: false
    property bool autoApprove: false

    property bool isLoading: false
    property string lastError: ""
    property var currentChat: []
    property string currentChatId: ""
    property real lastHudActivityAt: 0

    readonly property var pendingApproval: {
        const chat = currentChat || [];
        for (let i = chat.length - 1; i >= 0; i--) {
            const msg = chat[i];
            if ((msg.role === "approval" || msg.role === "diff") && msg.pending !== false)
                return msg;
        }
        return null;
    }
    readonly property bool approvalPending: pendingApproval !== null

    signal chatModelChanged
    signal modelSelectionRequested

    onChatModelChanged: ComputerUse.syncFromChat(approvalPending)
    onApprovalPendingChanged: ComputerUse.syncFromChat(approvalPending)

    Connections {
        target: ComputerUse
        function onSessionActiveChanged() {
            if (ComputerUse.sessionActive) {
                if (ComputerUse.workUserIndex < 0)
                    ComputerUse.workUserIndex = root.lastUserIndex();
                return;
            }
            root.endComputerUseGrant();
        }
        function onSessionFinished(userIndex, durationMs) {
            Qt.callLater(() => root.collapseComputerUseWork(userIndex, durationMs));
        }
    }

    NativeToolBridge {
        id: nativeBridge
        onResultReady: (callId, result) => root.writeCmd({
            cmd: "native_result",
            call_id: callId,
            result: result
        })
    }

    onCurrentModelChanged: {
        if (persistenceReady && currentModel && isRestored)
            StateService.set("lastAiModel", currentModel.model);
        if (agentReady && currentModel)
            writeCmd({ cmd: "set_model", model: modelPayload(currentModel) });
    }

    function restoreModel() {
        savedModelId = StateService.get("lastAiModel", Config.ai.defaultModel || "gemini-2.0-flash");
        tryRestore();
        persistenceReady = true;
    }

    function tryRestore() {
        if (models.length === 0)
            return;
        const wanted = savedModelId || Config.ai.defaultModel || "";
        if (wanted) {
            for (let i = 0; i < models.length; i++) {
                const m = models[i];
                if (root.modelIdOf(m) === wanted || m.name === wanted) {
                    currentModel = m;
                    isRestored = true;
                    return;
                }
            }
        }
        const defaults = Config.ai.defaultModels;
        if (defaults) {
            const order = ["openai", "anthropic", "gemini", "openrouter", "ollama", "custom"];
            for (let p = 0; p < order.length; p++) {
                const provider = order[p];
                const mid = root.providerDefault(provider);
                if (!mid)
                    continue;
                const found = findModel(mid, provider);
                if (found) {
                    currentModel = found;
                    isRestored = true;
                    return;
                }
            }
        }
        if (currentModel)
            isRestored = true;
        else if (models.length > 0) {
            currentModel = models[0];
            isRestored = true;
        }
    }

    function modelsFor(provider) {
        const out = [];
        const id = String(provider || "").toLowerCase();
        for (let i = 0; i < models.length; i++) {
            const m = models[i];
            if (m && String(m.provider || "").toLowerCase() === id)
                out.push(m);
        }
        return out;
    }

    function findModel(modelId, provider, keyId) {
        const mid = String(modelId || "");
        const pid = String(provider || "").toLowerCase();
        const kid = keyId !== undefined && keyId !== null ? String(keyId) : "";
        for (let i = 0; i < models.length; i++) {
            const m = models[i];
            if (!m)
                continue;
            if (mid && root.modelIdOf(m) !== mid)
                continue;
            if (pid && String(m.provider || "").toLowerCase() !== pid)
                continue;
            if (kid && String(m.key_id || "") !== kid)
                continue;
            return m;
        }
        return null;
    }

    function modelIdOf(m) {
        return m ? String(m.model || "") : "";
    }

    function isSameModel(a, b) {
        if (!a || !b)
            return false;
        return String(a.provider || "").toLowerCase() === String(b.provider || "").toLowerCase()
            && root.modelIdOf(a) === root.modelIdOf(b)
            && String(a.key_id || "") === String(b.key_id || "");
    }

    function providerDefault(provider) {
        const defaults = Config.ai.defaultModels;
        if (!defaults || !provider)
            return "";
        switch (String(provider).toLowerCase()) {
        case "openai":
            return defaults.openai || "";
        case "anthropic":
            return defaults.anthropic || "";
        case "gemini":
            return defaults.gemini || "";
        case "openrouter":
            return defaults.openrouter || "";
        case "ollama":
            return defaults.ollama || "";
        case "custom":
            return defaults.custom || "";
        default:
            return "";
        }
    }

    function setProviderDefault(provider, modelObj) {
        if (!provider || !modelObj)
            return;
        const mid = root.modelIdOf(modelObj);
        if (!mid)
            return;
        Config.setAiProviderDefault(provider, mid);
        currentModel = modelObj;
        savedModelId = mid;
        if (persistenceReady)
            StateService.set("lastAiModel", mid);
    }

    function selectModel(modelObj) {
        if (!modelObj)
            return;
        const provider = String(modelObj.provider || "").toLowerCase();
        if (provider)
            root.setProviderDefault(provider, modelObj);
        else {
            currentModel = modelObj;
            savedModelId = root.modelIdOf(modelObj);
            Config.ai.defaultModel = savedModelId;
            Config.saveAi();
            if (persistenceReady)
                StateService.set("lastAiModel", savedModelId);
        }
    }

    function setModel(modelName, provider, keyId) {
        const found = root.findModel(modelName, provider, keyId);
        if (found) {
            root.selectModel(found);
            return;
        }
        for (let i = 0; i < models.length; i++) {
            if (models[i].name === modelName || root.modelIdOf(models[i]) === String(modelName || "")) {
                root.selectModel(models[i]);
                return;
            }
        }
    }

    Connections {
        target: StateService
        function onStateLoaded() {
            restoreModel();
        }
    }

    Connections {
        target: KeyStore
        function onKeysChanged() {
            pruneModelsMissingKeys();
            sendInit();
            fetchAvailableModels();
        }
    }

    Connections {
        target: Config.ai
        function onCustomEndpointChanged() {
            fetchAvailableModels();
        }
        function onCustomModelsChanged() {
            fetchAvailableModels();
        }
        function onCustomModelsJsonChanged() {
            fetchAvailableModels();
        }
        function onCustomNameChanged() {
            fetchAvailableModels();
        }
        function onManualModelsJsonChanged() {
            fetchAvailableModels();
        }
    }

    Component.onCompleted: {
        if (StateService.initialized)
            restoreModel();
        createNewChat();
        agentProc.running = true;
        if (models.length === 0)
            seedFallbackModels();
        fetchAvailableModels();
    }

    function modelPayload(model) {
        if (!model)
            return {};
        return {
            name: model.name,
            model: model.model,
            provider: model.provider,
            endpoint: model.endpoint,
            key_id: model.key_id || model.provider
        };
    }

    function skillDirs() {
        const home = Quickshell.env("HOME") || "";
        const configHome = Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config");
        return [bundledSkills, configHome + "/ambxst+/ai/skills"];
    }

    function sendInit() {
        if (!agentProc.running)
            return;
        writeCmd({
            cmd: "init",
            workspace: Config.ai.workspace || (Quickshell.env("HOME") || ""),
            enabled_tools: Config.ai.enabledTools || [],
            execution_profile: {
                readFiles: Config.ai.executionProfile.readFiles,
                applyCodeDiffs: Config.ai.executionProfile.applyCodeDiffs,
                executeCommands: Config.ai.executionProfile.executeCommands,
                askUserQuestion: Config.ai.executionProfile.askUserQuestion,
                computerUse: Config.ai.executionProfile.computerUse,
                commandAllowlist: Config.ai.executionProfile.commandAllowlist,
                commandDenylist: Config.ai.executionProfile.commandDenylist,
                directoryAllowlist: Config.ai.executionProfile.directoryAllowlist,
                webSearchEnabled: Config.ai.executionProfile.webSearchEnabled
            },
            skill_dirs: skillDirs(),
            keystore_db: KeyStore.dbPath,
            custom_endpoint: Config.ai.customEndpoint || "",
            custom_models: Config.readManualModels("custom"),
            custom_name: Config.ai.customName || "",
            ignore_catalog: Config.readIgnoreCatalog(),
            manual_models: Config.readManualModelsMap(),
            model: modelPayload(currentModel),
            context: { autoexecute_any_action: autoApprove }
        });
    }

    function writeCmd(obj) {
        if (!agentProc.running)
            return;
        agentProc.write(JSON.stringify(obj) + "\n");
    }

    function desktopContext() {
        const parts = [];
        const providers = Config.ai.contextProviders;
        if (providers && providers.focusedWindow) {
            const win = AxctlService.focusedClient;
            if (win)
                parts.push("Focused window: " + (win.title || win.class_name || win.address || ""));
        }
        if (providers && providers.clipboard && ClipboardService.items && ClipboardService.items.length > 0)
            parts.push("Clipboard: " + String(ClipboardService.items[0].preview || "").slice(0, 200));
        if (providers && providers.notifications && Notifications.list) {
            const n = Notifications.list.slice(0, 5).map(x => (x.appName || "") + ": " + (x.summary || ""));
            if (n.length)
                parts.push("Notifications: " + n.join(" | "));
        }
        if (providers && providers.weather && WeatherService.dataAvailable)
            parts.push("Weather: " + WeatherService.weatherDescription + " " + WeatherService.currentTemp);
        if (providers && providers.resources)
            parts.push("CPU " + Math.round(SystemResources.cpuUsage) + "% RAM " + Math.round(SystemResources.ramUsage) + "%");
        return parts.join("\n");
    }

    function processCommand(text) {
        const cmd = text.trim();
        if (!cmd.startsWith("/"))
            return false;
        const parts = cmd.split(" ");
        const command = parts[0].toLowerCase();
        const args = parts.slice(1).join(" ");
        switch (command) {
        case "/new":
            createNewChat();
            return true;
        case "/model":
            if (args) {
                const q = args.toLowerCase();
                let found = root.findModel(args);
                if (!found) {
                    for (let i = 0; i < models.length; i++) {
                        if (models[i].name.toLowerCase() === q || root.modelIdOf(models[i]).toLowerCase() === q) {
                            found = models[i];
                            break;
                        }
                    }
                }
                if (found)
                    root.selectModel(found);
                pushSystemMessage(found ? ("Switched to " + currentModel.name) : ("Model '" + args + "' not found."));
            } else {
                modelSelectionRequested();
            }
            return true;
        case "/help":
            pushSystemMessage("**/new** new chat\n**/model [name]** switch model\n**/help** this message\nEnter send · Esc close · Ctrl+N new · Ctrl+R regenerate");
            return true;
        default:
            return false;
        }
    }

    function sendMessage(text, attachments) {
        if ((!text || text.trim() === "") && (!attachments || attachments.length === 0))
            return;
        if (processCommand(text))
            return;
        isLoading = true;
        lastError = "";
        lastHudActivityAt = Date.now();
        const userMsg = { role: "user", content: text };
        if (attachments && attachments.length > 0)
            userMsg.attachments = attachments;
        const next = currentChat.slice();
        next.push(userMsg);
        currentChat = next;
        chatModelChanged();
        sendInit();
        const ctx = desktopContext();
        writeCmd({
            cmd: "send",
            text: ctx ? (text + "\n\n[Desktop context]\n" + ctx) : text,
            attachments: attachments || [],
            chat_id: currentChatId
        });
    }

    function cancel() {
        writeCmd({ cmd: "cancel" });
        isLoading = false;
    }

    function approveTool(callId) {
        markCall(callId, { pending: false, status: "approved" }, ["approval", "diff"]);
        writeCmd({ cmd: "approve", call_id: callId });
    }

    function rejectTool(callId) {
        markCall(callId, { pending: false, status: "rejected" }, ["approval", "diff"]);
        writeCmd({ cmd: "reject", call_id: callId });
    }

    function approvePendingApproval() {
        if (pendingApproval && pendingApproval.call_id)
            approveTool(pendingApproval.call_id);
    }

    function rejectPendingApproval() {
        if (pendingApproval && pendingApproval.call_id)
            rejectTool(pendingApproval.call_id);
    }

    function endComputerUseGrant() {
        writeCmd({ cmd: "end_computer_use" });
    }

    function stopComputerUse() {
        cancel();
        endComputerUseGrant();
        ComputerUse.end({ restoreSpotlight: true });
    }

    function answerQuestions(callId, answers) {
        markCall(callId, { pending: false, status: "answered" }, ["question"]);
        writeCmd({ cmd: "answer_questions", call_id: callId, answers: answers });
    }

    function setAutoApprove(value) {
        autoApprove = !!value;
        writeCmd({ cmd: "set_autoapprove", value: autoApprove });
    }

    function lastUserIndex() {
        const chat = currentChat || [];
        for (let i = chat.length - 1; i >= 0; i--) {
            if (chat[i].role === "user")
                return i;
        }
        return -1;
    }

    function lastUserMessage() {
        for (let i = currentChat.length - 1; i >= 0; i--) {
            if (currentChat[i].role === "user")
                return currentChat[i].content || "";
        }
        return "";
    }

    function regenerateLast() {
        let idx = -1;
        for (let i = currentChat.length - 1; i >= 0; i--) {
            if (currentChat[i].role === "assistant" || currentChat[i].role === "tool_call" || currentChat[i].role === "cu_work") {
                idx = i;
                break;
            }
        }
        if (idx < 0)
            return;
        let cut = idx;
        while (cut > 0 && currentChat[cut - 1].role !== "user")
            cut--;
        currentChat = currentChat.slice(0, cut);
        chatModelChanged();
        const last = lastUserMessage();
        if (last) {
            isLoading = true;
            writeCmd({ cmd: "load_chat", messages: flattenChat(currentChat) });
            writeCmd({ cmd: "send", text: last, attachments: [], chat_id: currentChatId });
        }
    }

    function regenerateResponse(index) {
        if (index < 0 || index >= currentChat.length)
            return;
        currentChat = currentChat.slice(0, index);
        chatModelChanged();
        const last = lastUserMessage();
        if (last) {
            isLoading = true;
            writeCmd({ cmd: "load_chat", messages: flattenChat(currentChat) });
            writeCmd({ cmd: "send", text: last, chat_id: currentChatId });
        }
    }

    function flattenChat(chat) {
        const out = [];
        const list = chat || [];
        for (let i = 0; i < list.length; i++) {
            const msg = list[i];
            if (msg && msg.role === "cu_work") {
                const nested = flattenChat(msg.items || []);
                for (let j = 0; j < nested.length; j++)
                    out.push(nested[j]);
                continue;
            }
            out.push(msg);
        }
        return out;
    }

    function collapseComputerUseWork(userIndex, durationMs) {
        const chat = currentChat || [];
        if (userIndex < 0 || userIndex >= chat.length)
            return;
        if (chat[userIndex].role !== "user")
            return;
        if (userIndex + 1 < chat.length && chat[userIndex + 1].role === "cu_work")
            return;
        let lastAsst = -1;
        for (let i = chat.length - 1; i > userIndex; i--) {
            if (chat[i].role === "assistant" && String(chat[i].content || "").trim()) {
                lastAsst = i;
                break;
            }
        }
        const endExclusive = lastAsst > userIndex ? lastAsst : chat.length;
        const items = [];
        for (let i = userIndex + 1; i < endExclusive; i++)
            items.push(chat[i]);
        if (!items.length)
            return;
        const next = chat.slice(0, userIndex + 1);
        next.push({
            role: "cu_work",
            durationMs: durationMs,
            items: items
        });
        for (let i = endExclusive; i < chat.length; i++)
            next.push(chat[i]);
        currentChat = next;
        chatModelChanged();
    }

    function updateMessage(index, newContent) {
        if (index < 0 || index >= currentChat.length)
            return;
        const next = currentChat.slice();
        next[index] = Object.assign({}, next[index], { content: newContent });
        currentChat = next;
        chatModelChanged();
    }

    function pushSystemMessage(text) {
        const next = currentChat.slice();
        next.push({ role: "system", content: text });
        currentChat = next;
        chatModelChanged();
    }

    function createNewChat() {
        if (ComputerUse.sessionActive) {
            endComputerUseGrant();
            ComputerUse.end({ restoreSpotlight: true });
        }
        currentChat = [];
        currentChatId = Date.now().toString();
        // Session-scoped: each new chat starts in auto-review (ask before risky actions).
        if (autoApprove)
            setAutoApprove(false);
        else
            autoApprove = false;
        chatModelChanged();
        if (agentReady)
            writeCmd({ cmd: "load_chat", messages: [] });
    }

    function markCall(callId, patch, roles) {
        const next = [];
        const dropResolvedGate = patch && patch.pending === false;
        for (let i = 0; i < currentChat.length; i++) {
            const msg = currentChat[i];
            if (msg.call_id !== callId) {
                next.push(msg);
                continue;
            }
            if (roles && roles.indexOf(msg.role) < 0) {
                next.push(msg);
                continue;
            }
            // Drop resolved approval/diff/question cards so they don't leave blank ListView gaps.
            if (dropResolvedGate && (msg.role === "approval" || msg.role === "diff" || msg.role === "question"))
                continue;
            next.push(Object.assign({}, msg, patch));
        }
        currentChat = next;
        chatModelChanged();
    }

    function appendToken(text) {
        lastHudActivityAt = Date.now();
        const next = currentChat.slice();
        const last = next.length ? next[next.length - 1] : null;
        if (last && last.role === "assistant" && last.streaming) {
            next[next.length - 1] = Object.assign({}, last, { content: (last.content || "") + text });
        } else {
            next.push({ role: "assistant", content: text, streaming: true, model: currentModel ? currentModel.name : "" });
        }
        currentChat = next;
        chatModelChanged();
    }

    function applyEvent(ev) {
        if (!ev || !ev.type)
            return;
        switch (ev.type) {
        case "token":
            appendToken(ev.text || "");
            break;
        case "tool_call":
            {
                const next = currentChat.slice();
                next.push({
                    role: "tool_call",
                    name: ev.name,
                    call_id: ev.call_id,
                    args: ev.args || {},
                    status: "running",
                    user_friendly_name: ev.user_friendly_name || ev.name,
                    user_friendly_done: ev.user_friendly_done || ev.user_friendly_name || ev.name
                });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "tool_result":
            {
                const patch = { status: ev.status || "done", result: ev.result };
                if (ev.result && ev.result.path)
                    patch.previewPath = ev.result.path;
                markCall(ev.call_id, patch);
            }
            break;
        case "approval_required":
            {
                const next = currentChat.slice();
                next.push({
                    role: "approval",
                    call_id: ev.call_id,
                    name: ev.name,
                    args: ev.args || {},
                    user_friendly_name: ev.user_friendly_name || ev.name,
                    detail: typeof ev.args === "object" ? JSON.stringify(ev.args) : String(ev.args || ""),
                    pending: true
                });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "diff_preview":
            {
                const next = currentChat.slice();
                next.push({
                    role: "diff",
                    call_id: ev.call_id,
                    name: ev.name,
                    previews: ev.previews || [],
                    edits: ev.edits || [],
                    user_friendly_name: ev.user_friendly_name || qsTr("Review file edits"),
                    pending: true
                });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "ask_user_question":
            {
                const next = currentChat.slice();
                next.push({
                    role: "question",
                    call_id: ev.call_id,
                    items: ev.items || [],
                    user_friendly_name: ev.user_friendly_name || qsTr("Question"),
                    pending: true
                });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "native_request":
            nativeBridge.handle(ev.name, ev.args || {}, ev.call_id);
            break;
        case "done":
            if (ev.reason === "init") {
                agentReady = true;
                writeCmd({ cmd: "list_models" });
                return;
            }
            if (!ev.reason) {
                isLoading = false;
                const next = currentChat.slice();
                if (next.length && next[next.length - 1].streaming)
                    next[next.length - 1] = Object.assign({}, next[next.length - 1], { streaming: false });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "cancelled":
            isLoading = false;
            chatModelChanged();
            break;
        case "error":
            lastError = ev.error || "error";
            isLoading = false;
            pushSystemMessage("Error: " + lastError);
            break;
        case "models":
            ingestModels(ev.models || []);
            fetchingModels = false;
            break;
        }
    }

    function fetchAvailableModels() {
        fetchingModels = true;
        if (agentReady) {
            sendInit();
            writeCmd({ cmd: "list_models" });
        } else {
            pruneModelsMissingKeys();
            seedFallbackModels();
            fetchingModels = false;
        }
    }

    function modelStillAvailable(m) {
        if (!m)
            return false;
        const provider = String(m.provider || "").toLowerCase();
        if (!provider)
            return true;
        if (KeyStore.hasKey(provider))
            return true;
        const mid = root.modelIdOf(m);
        const manuals = Config.readManualModels(provider);
        for (let i = 0; i < manuals.length; i++) {
            const item = manuals[i] || {};
            if (String(item.model || item.id || "") === mid)
                return true;
        }
        if (m.requires_key === false)
            return false;
        return false;
    }

    function pruneModelsMissingKeys() {
        const next = [];
        let droppedCurrent = false;
        for (let i = 0; i < models.length; i++) {
            const m = models[i];
            if (modelStillAvailable(m)) {
                next.push(m);
                continue;
            }
            if (currentModel === m)
                droppedCurrent = true;
            if (m && m.destroy)
                m.destroy();
        }
        if (next.length !== models.length)
            models = next;
        if (droppedCurrent || (currentModel && next.indexOf(currentModel) === -1)) {
            currentModel = next.length > 0 ? next[0] : null;
            isRestored = !!currentModel;
        }
    }

    function manualEndpoint(provider) {
        switch (String(provider || "").toLowerCase()) {
        case "openai":
            return "https://api.openai.com";
        case "openrouter":
            return "https://openrouter.ai/api/v1";
        case "anthropic":
            return "https://api.anthropic.com";
        case "gemini":
            return "https://generativelanguage.googleapis.com/v1beta";
        case "ollama":
            return "http://127.0.0.1:11434";
        case "custom":
            return Config.ai.customEndpoint || "";
        default:
            return "";
        }
    }

    function seedFallbackModels() {
        const seeded = [];
        const extras = Config.ai.extraModels || [];
        for (let i = 0; i < extras.length; i++) {
            const item = extras[i] || {};
            seeded.push(aiModelFactory.createObject(root, {
                name: item.name || item.model || "custom",
                description: item.description || "",
                endpoint: item.endpoint || Config.ai.customEndpoint || "",
                model: item.model || item.name || "",
                provider: item.provider || "custom",
                requires_key: item.requires_key !== false,
                key_id: item.key_id || item.provider || "custom"
            }));
        }
        const providers = ["openai", "anthropic", "gemini", "openrouter", "ollama", "custom"];
        for (let p = 0; p < providers.length; p++) {
            const provider = providers[p];
            const items = Config.readManualModels(provider);
            const customLabel = provider === "custom" ? (Config.ai.customName || "") : "";
            for (let i = 0; i < items.length; i++) {
                const item = items[i] || {};
                const mid = item.model || item.id || "";
                if (!mid)
                    continue;
                seeded.push(aiModelFactory.createObject(root, {
                    name: item.name || customLabel || mid,
                    description: item.description || customLabel || provider,
                    endpoint: root.manualEndpoint(provider),
                    model: mid,
                    provider: provider,
                    requires_key: provider !== "ollama",
                    key_id: provider
                }));
            }
        }
        if (seeded.length)
            mergeModels(seeded);
    }

    function ingestModels(list) {
        const previous = currentModel ? {
            model: currentModel.model,
            provider: currentModel.provider,
            key_id: currentModel.key_id || ""
        } : null;
        const created = [];
        for (let i = 0; i < list.length; i++) {
            const item = list[i] || {};
            created.push(aiModelFactory.createObject(root, {
                name: item.name || item.model,
                description: item.description || "",
                endpoint: item.endpoint || "",
                model: item.model,
                provider: item.provider,
                requires_key: item.requires_key !== false,
                key_id: item.key_id || item.provider
            }));
        }
        for (let i = 0; i < models.length; i++) {
            if (models[i] && models[i].destroy)
                models[i].destroy();
        }
        models = created;
        seedFallbackModels();
        isRestored = false;
        if (previous) {
            const match = findModel(previous.model, previous.provider, previous.key_id)
                || findModel(previous.model, previous.provider);
            if (match) {
                currentModel = match;
                isRestored = true;
            }
        }
        tryRestore();
    }

    function mergeModels(newModels) {
        const updated = [];
        for (let i = 0; i < models.length; i++)
            updated.push(models[i]);
        for (let i = 0; i < newModels.length; i++) {
            const m = newModels[i];
            let dup = false;
            for (let j = 0; j < updated.length; j++) {
                if (root.modelIdOf(updated[j]) === root.modelIdOf(m) && (updated[j].key_id || "") === (m.key_id || "") && String(updated[j].provider || "").toLowerCase() === String(m.provider || "").toLowerCase()) {
                    dup = true;
                    break;
                }
            }
            if (!dup)
                updated.push(m);
            else if (m.destroy)
                m.destroy();
        }
        models = updated;
        if (!isRestored)
            tryRestore();
    }

    Process {
        id: agentProc
        command: ["python3", "-u", root.agentScript]
        running: false
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                const line = data ? String(data).trim() : "";
                if (!line)
                    return;
                Qt.callLater(() => {
                    try {
                        root.applyEvent(JSON.parse(line));
                    } catch (e) {
                        console.warn("Ai: bad agent event", e, line);
                    }
                });
            }
        }
        onStarted: {
            root.agentReady = false;
            root.sendInit();
        }
        onExited: () => {
            root.agentReady = false;
            if (root.isLoading) {
                root.isLoading = false;
                root.pushSystemMessage("Agent process exited.");
            }
            agentRestart.restart();
        }
    }

    Timer {
        id: agentRestart
        interval: 800
        repeat: false
        onTriggered: agentProc.running = true
    }

    Component {
        id: aiModelFactory
        AiModel {}
    }
}
