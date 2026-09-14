.pragma library

var data = {
    "systemPrompt": "You are a helpful assistant running on Ambxst[+], a Linux desktop shell. Prefer specialized tools over guessing. Use grep to locate, then read_files with line ranges. Edit via apply_file_diffs, not whole-file rewrites. Ask the user when intent is ambiguous.",
    "defaultModel": "gemini-2.0-flash",
    "customEndpoint": "",
    "customCurlTemplate": "",
    "extraModels": [],
    "workspace": "",
    "overlayWidth": 640,
    "overlayYFraction": 0.22,
    "showScrim": true,
    "temperature": 0.7,
    "maxTokens": 4096,
    "enabledTools": [
        "read_files",
        "grep",
        "file_glob",
        "apply_file_diffs",
        "run_shell_command",
        "ask_user_question",
        "read_skill",
        "exa_search",
        "exa_contents",
        "native"
    ],
    "commands": [],
    "contextProviders": {
        "focusedWindow": true,
        "clipboard": false,
        "notifications": false,
        "weather": false,
        "resources": false
    },
    "executionProfile": {
        "readFiles": "AgentDecides",
        "applyCodeDiffs": "AlwaysAsk",
        "executeCommands": "AlwaysAsk",
        "askUserQuestion": "AlwaysAsk",
        "computerUse": "Never",
        "commandAllowlist": [
            "cat(\\s.*)?",
            "echo(\\s.*)?",
            "find .*",
            "grep(\\s.*)?",
            "ls(\\s.*)?",
            "which .*"
        ],
        "commandDenylist": [
            "bash(\\s.*)?",
            "fish(\\s.*)?",
            "pwsh(\\s.*)?",
            "sh(\\s.*)?",
            "zsh(\\s.*)?",
            "curl(\\s.*)?",
            "eval(\\s.*)?",
            "exec(\\s.*)?",
            "source(\\s.*)?",
            "wget(\\s.*)?",
            "dig(\\s.*)?",
            "nslookup(\\s.*)?",
            "host(\\s.*)?",
            "ssh(\\s.*)?",
            "scp(\\s.*)?",
            "rsync(\\s.*)?",
            "telnet(\\s.*)?",
            "rm(\\s.*)?"
        ],
        "directoryAllowlist": [],
        "webSearchEnabled": true
    }
}
