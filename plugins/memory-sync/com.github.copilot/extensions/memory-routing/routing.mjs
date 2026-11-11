import { execFile } from "node:child_process";
import { access, realpath } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const SERVER = "agent-memory-mcp";

export async function workspaceRoot(cwd) {
    if (typeof cwd !== "string" || !path.isAbsolute(cwd)) {
        throw new Error("session did not supply an absolute working directory");
    }
    const { stdout } = await execFileAsync("git", ["-C", cwd, "rev-parse", "--show-toplevel"], {
        timeout: 10000,
        windowsHide: true,
    });
    const root = await realpath(stdout.trim());
    await access(path.join(root, ".memory-store.json"));
    return root;
}

export function isMemoryTool(name) {
    return typeof name === "string" && (
        name.startsWith(`${SERVER}-`) ||
        name.startsWith("agent_memory_mcp_") ||
        name.startsWith(`mcp__${SERVER}__`)
    );
}

function timeout(promise, milliseconds) {
    let timer;
    return Promise.race([
        promise,
        new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error("memory routing timed out")), milliseconds);
        }),
    ]).finally(() => clearTimeout(timer));
}

export function createRouter(session, pluginRoot, options = {}) {
    const resolveRoot = options.resolveRoot ?? workspaceRoot;
    const timeoutMs = options.timeoutMs ?? 30000;
    const pollIntervalMs = options.pollIntervalMs ?? 250;
    let active;
    let boundRoot;

    async function waitForReady() {
        const deadline = Date.now() + timeoutMs;
        let lastStatus = "unknown";
        while (Date.now() < deadline) {
            const { servers } = await session.rpc.mcp.listConfigured();
            const entry = servers.find((item) => item.name === SERVER);
            if (!entry || !entry.enabled || entry.source !== "plugin" || entry.sourcePlugin !== "memory-sync") {
                throw new Error("the enabled memory-sync server registration disappeared");
            }
            lastStatus = entry.live?.status ?? "unavailable";
            if (lastStatus === "failed") {
                if (entry.live.error) lastStatus = `failed: ${entry.live.error}`;
            }
            if (entry.live?.status === "connected" && entry.live.toolsLoaded === true) return;
            await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
        }
        throw new Error(`memory server did not become ready (status: ${lastStatus})`);
    }

    async function bind() {
        for (let attempt = 0; attempt < 3; attempt++) {
            const metadata = await session.rpc.metadata.snapshot();
            const { servers } = await session.rpc.mcp.listConfigured();
            const matches = servers.filter((item) => item.name === SERVER);
            if (matches.length > 1) {
                throw new Error("multiple memory server registrations; resolve the duplicate before use");
            }
            const entry = matches[0];
            if (!entry || !entry.enabled || entry.source !== "plugin" || entry.sourcePlugin !== "memory-sync") {
                boundRoot = undefined;
                return false;
            }
            if (servers.some((item) => item.name !== SERVER && item.enabled &&
                (item.name.startsWith(`${SERVER}-`) ||
                    (item.source === "plugin" && item.sourcePlugin === "memory-sync")))) {
                throw new Error("multiple memory server registrations; resolve the duplicate before use");
            }
            const root = await resolveRoot(metadata.workingDirectory);
            const ready = entry.live?.status === "connected" && entry.live.toolsLoaded === true;
            if (boundRoot !== root || !ready) {
                boundRoot = undefined;
                await session.rpc.mcp.restartServer({
                    serverName: SERVER,
                    config: {
                        type: "stdio",
                        command: "uv",
                        args: ["run", "--no-project", "--quiet", path.join(pluginRoot, "bin", "memory-store.py"), "serve", "--workspace", root],
                        cwd: root,
                    },
                });
                await waitForReady();
            }
            const current = await session.rpc.metadata.snapshot();
            if (await resolveRoot(current.workingDirectory) === root) {
                boundRoot = root;
                return true;
            }
            boundRoot = undefined;
        }
        throw new Error("session working directory changed repeatedly while routing memory");
    }

    function ensureReady() {
        if (!active) {
            const pending = bind();
            active = pending;
            pending.finally(() => {
                if (active === pending) active = undefined;
            }).catch(() => {});
        }
        return timeout(active, timeoutMs);
    }

    return {
        ensureReady,
        invalidate() {
            if (!active) boundRoot = undefined;
        },
        async preToolUse(input) {
            if (!isMemoryTool(input.toolName)) return;
            try {
                await ensureReady();
            } catch (error) {
                return {
                    permissionDecision: "deny",
                    permissionDecisionReason: `Memory workspace routing is not ready: ${error.message}`,
                };
            }
        },
    };
}
