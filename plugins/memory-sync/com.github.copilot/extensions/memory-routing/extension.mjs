import { joinSession } from "@github/copilot-sdk/extension";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRouter, isMemoryTool } from "./routing.mjs";

let router;
const session = await joinSession({
    hooks: {
        onPreToolUse: async (input) => {
            if (router) return router.preToolUse(input);
            if (isMemoryTool(input.toolName)) {
                return {
                    permissionDecision: "deny",
                    permissionDecisionReason: "Memory workspace routing is still starting.",
                };
            }
        },
    },
});
const pluginRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
router = createRouter(session, pluginRoot);

async function route(retries = 0) {
    try {
        await router.ensureReady();
    } catch (error) {
        await session.log(`Memory workspace routing failed: ${error.message}`, { level: "error" });
        if (retries < 5) setTimeout(() => { void route(retries + 1); }, 5000);
    }
}

session.on("session.context_changed", () => { void route(); });
session.on("session.mcp_server_status_changed", (event) => {
    if (event.data.serverName === "agent-memory-mcp" &&
        ["failed", "stopped", "disabled", "not_configured"].includes(event.data.status)) {
        router.invalidate();
    }
});
void route();
