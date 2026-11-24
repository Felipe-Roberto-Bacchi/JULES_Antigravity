# Jules Pet Bridge (`jules-pet-bridge`)

Native Antigravity plugin that connects Antigravity lifecycle and tool hooks to **Jules Desktop Pet** over loopback TCP (`127.0.0.1:18765`, JSON-Lines).

## What It Forwards

- `SessionStart`, `PreInvocation`, `PostInvocation`, `Stop` → `lifecycle` events (including `transcriptPath`, `terminationReason`, and `fullyIdle`)
- `PreToolUse` (`matcher: "*"`) → `tool_start` events (or synchronous `approval_request` on `run_command` when `JULES_PET_APPROVAL_BRIDGE=1`)
- `PostToolUse` (`matcher: "*"`) → `tool_end` events (including `error` status)

If Jules Desktop Pet is offline, `hook_bridge.py` fails open within ~80 ms (`{}` for lifecycle/post hooks, `{"decision": "ask"}` for `PreToolUse`).

## Installation

### Global Installation (All Workspaces)

Copy the `plugins/jules-pet-bridge/` directory into your Antigravity global plugins directory:

**Windows (PowerShell):**
```powershell
Copy-Item -Recurse -Force ".\plugins\jules-pet-bridge" "$HOME\.gemini\config\plugins\jules-pet-bridge"
```

**macOS / Linux:**
```bash
mkdir -p ~/.gemini/config/plugins
cp -r ./plugins/jules-pet-bridge ~/.gemini/config/plugins/jules-pet-bridge
```

### Workspace-Scoped Installation

Alternatively, copy the folder into `.agents/plugins/jules-pet-bridge/` inside a specific repository.

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `JULES_PET_HOST` | `127.0.0.1` | Loopback host where Jules Desktop Pet listens |
| `JULES_PET_PORT` | `18765` | TCP port where Jules Desktop Pet listens |
| `JULES_PET_APPROVAL_BRIDGE` | `0` | Set to `1` to route `run_command` `PreToolUse` approvals to the pet |
| `JULES_APPROVAL_TIMEOUT` | `20` | Seconds to wait for pet approval before falling back to `"ask"` |
