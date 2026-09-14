pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import qs.config
import qs.modules.services
import "ai"

Singleton {
    id: root

    property string chatDir: Quickshell.env("HOME") + "/.local/share/ambxst+/chats"
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
    property var chatHistory: []

    signal chatModelChanged
    signal historyModelChanged
    signal modelSelectionRequested

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
        if (isRestored || models.length === 0)
            return;
        for (let i = 0; i < models.length; i++) {
            const m = models[i];
            if (m.model === savedModelId || m.model.endsWith("/" + savedModelId) || m.name === savedModelId) {
                currentModel = m;
                isRestored = true;
                return;
            }
        }
        if (currentModel)
            isRestored = true;
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
            fetchAvailableModels();
        }
    }

    Component.onCompleted: {
        if (StateService.initialized)
            restoreModel();
        reloadHistory();
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
            system_prompt: Config.ai.systemPrompt || "",
            temperature: Config.ai.temperature ?? 0.7,
            max_tokens: Config.ai.maxTokens ?? 4096,
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
                let found = false;
                for (let i = 0; i < models.length; i++) {
                    if (models[i].name.toLowerCase().includes(args.toLowerCase()) || models[i].model.toLowerCase() === args.toLowerCase()) {
                        setModel(models[i].name);
                        found = true;
                        break;
                    }
                }
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
        const userMsg = { role: "user", content: text };
        if (attachments && attachments.length > 0)
            userMsg.attachments = attachments;
        const next = currentChat.slice();
        next.push(userMsg);
        currentChat = next;
        chatModelChanged();
        saveCurrentChat();
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
        markCall(callId, { pending: false, status: "approved" });
        writeCmd({ cmd: "approve", call_id: callId });
    }

    function rejectTool(callId) {
        markCall(callId, { pending: false, status: "rejected" });
        writeCmd({ cmd: "reject", call_id: callId });
    }

    function answerQuestions(callId, answers) {
        markCall(callId, { pending: false, status: "answered" });
        writeCmd({ cmd: "answer_questions", call_id: callId, answers: answers });
    }

    function setAutoApprove(value) {
        autoApprove = !!value;
        writeCmd({ cmd: "set_autoapprove", value: autoApprove });
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
            if (currentChat[i].role === "assistant" || currentChat[i].role === "tool_call") {
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
            writeCmd({ cmd: "load_chat", messages: currentChat });
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
            writeCmd({ cmd: "load_chat", messages: currentChat });
            writeCmd({ cmd: "send", text: last, chat_id: currentChatId });
        }
    }

    function updateMessage(index, newContent) {
        if (index < 0 || index >= currentChat.length)
            return;
        const next = currentChat.slice();
        next[index] = Object.assign({}, next[index], { content: newContent });
        currentChat = next;
        saveCurrentChat();
        chatModelChanged();
    }

    function setModel(modelName) {
        for (let i = 0; i < models.length; i++) {
            if (models[i].name === modelName) {
                currentModel = models[i];
                return;
            }
        }
    }

    function pushSystemMessage(text) {
        const next = currentChat.slice();
        next.push({ role: "system", content: text });
        currentChat = next;
        chatModelChanged();
    }

    function createNewChat() {
        currentChat = [];
        currentChatId = Date.now().toString();
        autoApprove = false;
        chatModelChanged();
        if (agentReady)
            writeCmd({ cmd: "load_chat", messages: [] });
    }

    function deleteChat(id) {
        if (id === currentChatId)
            createNewChat();
        deleteChatProcess.command = ["rm", chatDir + "/" + id + ".json"];
        deleteChatProcess.running = true;
    }

    function saveCurrentChat() {
        if (currentChat.length === 0)
            return;
        saveChatProcess.filePath = chatDir + "/" + currentChatId + ".json";
        saveChatProcess.data = JSON.stringify(currentChat, null, 2);
        saveChatProcess.command = ["/usr/bin/mkdir", "-p", chatDir];
        saveChatProcess.running = true;
    }

    function reloadHistory() {
        const py = `import os, json, glob
chat_dir = ${JSON.stringify(chatDir)}
os.makedirs(chat_dir, exist_ok=True)
files = sorted(glob.glob(chat_dir + "/*.json"), key=os.path.getmtime, reverse=True)
for f in files:
    id = os.path.basename(f)[:-5]
    title = "New Chat"
    try:
        with open(f) as fp:
            data = json.load(fp)
            for msg in data:
                if msg.get("role") == "user":
                    title = msg.get("content", "")[:40].replace("\\n", " ").strip()
                    if len(msg.get("content", "")) > 40: title += "..."
                    break
    except Exception:
        pass
    print(f"{id}|{title}")
`;
        listHistoryProcess.command = ["python3", "-c", py];
        listHistoryProcess.running = true;
    }

    function loadChat(id) {
        loadChatProcess.targetId = id;
        loadChatProcess.command = ["cat", chatDir + "/" + id + ".json"];
        loadChatProcess.running = true;
    }

    function markCall(callId, patch) {
        const next = currentChat.slice();
        for (let i = 0; i < next.length; i++) {
            if (next[i].call_id === callId)
                next[i] = Object.assign({}, next[i], patch);
        }
        currentChat = next;
        chatModelChanged();
    }

    function appendToken(text) {
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
                    user_friendly_name: ev.user_friendly_name || ev.name
                });
                currentChat = next;
                chatModelChanged();
            }
            break;
        case "tool_result":
            markCall(ev.call_id, { status: ev.status || "done", result: ev.result });
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
                saveCurrentChat();
                reloadHistory();
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
        if (agentReady)
            writeCmd({ cmd: "list_models" });
        else
            seedFallbackModels();
    }

    function seedFallbackModels() {
        const extras = Config.ai.extraModels || [];
        const seeded = [];
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
        if (seeded.length)
            mergeModels(seeded);
    }

    function ingestModels(list) {
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
        mergeModels(created);
        seedFallbackModels();
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
                if (updated[j].model === m.model) {
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

    FileView {
        id: chatFileView
        printErrors: false
    }

    Process {
        id: saveChatProcess
        property string filePath: ""
        property string data: ""
        onExited: exitCode => {
            if (exitCode === 0 && filePath.length > 0) {
                chatFileView.path = filePath;
                if (data.length > 0)
                    chatFileView.setText(data);
            }
        }
    }

    Process {
        id: listHistoryProcess
        stdout: StdioCollector {
            id: historyOut
        }
        onExited: () => {
            Qt.callLater(() => {
                const lines = historyOut.text.trim().split("\n").filter(l => l.length);
                const hist = [];
                for (let i = 0; i < lines.length; i++) {
                    const sp = lines[i].split("|");
                    hist.push({ id: sp[0], title: sp.slice(1).join("|") });
                }
                root.chatHistory = hist;
                root.historyModelChanged();
            });
        }
    }

    Process {
        id: loadChatProcess
        property string targetId: ""
        stdout: StdioCollector {
            id: loadOut
        }
        onExited: exitCode => {
            if (exitCode !== 0)
                return;
            Qt.callLater(() => {
                try {
                    root.currentChat = JSON.parse(loadOut.text);
                    root.currentChatId = targetId;
                    root.chatModelChanged();
                    root.writeCmd({ cmd: "load_chat", messages: root.currentChat });
                } catch (e) {
                    console.warn("Ai: failed to load chat", e);
                }
            });
        }
    }

    Process {
        id: deleteChatProcess
        onExited: () => root.reloadHistory()
    }

    Component {
        id: aiModelFactory
        AiModel {}
    }
}
