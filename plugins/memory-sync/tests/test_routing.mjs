import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, mkdir, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import test from "node:test";
import path from "node:path";
import { createRouter, workspaceRoot } from "../com.github.copilot/extensions/memory-routing/routing.mjs";

const root = path.resolve("plugin-root");
const workspace = path.resolve("worktree");
const other = path.resolve("other-worktree");

function fakeSession() {
    let cwd = workspace;
    let configured = [{
        name: "agent-memory-mcp",
        source: "plugin",
        sourcePlugin: "memory-sync",
        enabled: true,
        live: { status: "connected", toolsLoaded: true },
    }];
    const calls = [];
    return {
        calls,
        setCwd(value) { cwd = value; },
        setConfigured(value) { configured = value; },
        rpc: {
            metadata: { snapshot: async () => ({ workingDirectory: cwd }) },
            mcp: {
                listConfigured: async () => ({ servers: configured }),
                restartServer: async (request) => { calls.push(request); },
            },
        },
    };
}

function router(session, options = {}) {
    return createRouter(session, root, { resolveRoot: async (cwd) => cwd, ...options });
}

test("resolves real git worktrees separately and requires workspace config", async () => {
    const temp = await mkdtemp(path.join(os.tmpdir(), "memory-route-test-"));
    try {
        const main = path.join(temp, "main");
        const child = path.join(temp, "child");
        await mkdir(main);
        execFileSync("git", ["init", "-q", main]);
        execFileSync("git", ["-C", main, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "--allow-empty", "-qm", "test\n\nCo-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>"]);
        execFileSync("git", ["-C", main, "worktree", "add", "-qb", "test-child", child]);
        await writeFile(path.join(main, ".memory-store.json"), "{}");
        await writeFile(path.join(child, ".memory-store.json"), "{}");
        const sub = path.join(child, "nested");
        await mkdir(sub);
        assert.equal(await workspaceRoot(main), await realpath(main));
        assert.equal(await workspaceRoot(sub), await realpath(child));
        await rm(path.join(child, ".memory-store.json"));
        await assert.rejects(workspaceRoot(child));
    } finally {
        await rm(temp, { recursive: true, force: true });
    }
});

test("binds the current worktree with an explicit argument and no placeholder", async () => {
    const session = fakeSession();
    assert.equal(await router(session).ensureReady(), true);
    const request = session.calls[0];
    assert.equal(request.serverName, "agent-memory-mcp");
    assert.equal(request.config.cwd, workspace);
    assert.deepEqual(request.config.args.slice(-2), ["--workspace", workspace]);
    assert.equal(request.config.env, undefined);
    assert.ok(!request.config.args.includes("${workspaceFolder}"));
});

test("rebinding follows changed session cwd and concurrent requests share work", async () => {
    const session = fakeSession();
    const binding = router(session);
    await Promise.all([binding.ensureReady(), binding.ensureReady()]);
    assert.equal(session.calls.length, 1);
    session.setCwd(other);
    await binding.ensureReady();
    assert.equal(session.calls.length, 2);
    assert.equal(session.calls[1].config.cwd, other);
});

test("retries when the workspace changes during a restart", async () => {
    const session = fakeSession();
    session.rpc.mcp.restartServer = async (request) => {
        session.calls.push(request);
        if (session.calls.length === 1) session.setCwd(other);
    };
    assert.equal(await router(session).ensureReady(), true);
    assert.deepEqual(session.calls.map((call) => call.config.cwd), [workspace, other]);
});

test("does not override disabled, user or managed registrations", async () => {
    for (const entry of [
        { name: "agent-memory-mcp", source: "plugin", sourcePlugin: "memory-sync", enabled: false },
        { name: "agent-memory-mcp", source: "user", enabled: true },
        { name: "agent-memory-mcp", source: "managed", enabled: true },
    ]) {
        const session = fakeSession();
        session.setConfigured([entry]);
        assert.equal(await router(session).ensureReady(), false);
        assert.equal(session.calls.length, 0);
    }
});

test("refuses duplicate plugin server names", async () => {
    const session = fakeSession();
    session.setConfigured([
        { name: "agent-memory-mcp", source: "plugin", sourcePlugin: "memory-sync", enabled: true },
        { name: "agent-memory-mcp-2", source: "plugin", sourcePlugin: "memory-sync", enabled: true },
    ]);
    await assert.rejects(router(session).ensureReady(), /multiple memory server/);
    assert.equal(session.calls.length, 0);
});

test("refuses duplicate registrations with the same server name", async () => {
    const session = fakeSession();
    session.setConfigured([
        { name: "agent-memory-mcp", source: "plugin", sourcePlugin: "memory-sync", enabled: true },
        { name: "agent-memory-mcp", source: "user", enabled: true },
    ]);
    await assert.rejects(router(session).ensureReady(), /multiple memory server/);
    assert.equal(session.calls.length, 0);
});

test("rebinds after an external server lifecycle change", async () => {
    const session = fakeSession();
    const binding = router(session);
    await binding.ensureReady();
    binding.invalidate();
    await binding.ensureReady();
    assert.equal(session.calls.length, 2);
});

test("denies only memory tools when routing fails", async () => {
    const session = fakeSession();
    const binding = router(session, { resolveRoot: async () => { throw new Error("workspace unavailable"); } });
    assert.equal(await binding.preToolUse({ toolName: "unrelated" }), undefined);
    const denied = await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" });
    assert.equal(denied.permissionDecision, "deny");
    assert.match(denied.permissionDecisionReason, /workspace unavailable/);
    assert.equal(session.calls.length, 0);
});

test("timeout denies a memory call without launching overlapping retries", async () => {
    const session = fakeSession();
    session.rpc.mcp.restartServer = () => {
        session.calls.push("restart");
        return new Promise(() => {});
    };
    const binding = router(session, { timeoutMs: 10 });
    const first = await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" });
    const second = await binding.preToolUse({ toolName: "agent-memory-mcp-store_memory" });
    assert.equal(first.permissionDecision, "deny");
    assert.equal(second.permissionDecision, "deny");
    assert.deepEqual(session.calls, ["restart"]);
});

test("later memory calls retry after a failed startup", async () => {
    const session = fakeSession();
    let attempts = 0;
    session.rpc.mcp.restartServer = async () => {
        if (++attempts === 1) throw new Error("not ready");
    };
    const binding = router(session);
    assert.equal((await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" })).permissionDecision, "deny");
    assert.equal(await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" }), undefined);
    assert.equal(attempts, 2);
});

test("waits for the restarted server to load its tools before allowing calls", async () => {
    const session = fakeSession();
    let polls = 0;
    session.rpc.mcp.listConfigured = async () => ({
        servers: [{
            name: "agent-memory-mcp",
            source: "plugin",
            sourcePlugin: "memory-sync",
            enabled: true,
            live: ++polls < 3
                ? { status: "pending", toolsLoaded: false }
                : { status: "connected", toolsLoaded: true },
        }],
    });
    const binding = router(session, { pollIntervalMs: 1 });
    assert.equal(await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" }), undefined);
    assert.ok(polls >= 3);
});

test("denies calls when the server never becomes ready", async () => {
    const session = fakeSession();
    session.rpc.mcp.listConfigured = async () => ({
        servers: [{
            name: "agent-memory-mcp",
            source: "plugin",
            sourcePlugin: "memory-sync",
            enabled: true,
            live: { status: "pending", toolsLoaded: false },
        }],
    });
    const binding = router(session, { timeoutMs: 5, pollIntervalMs: 1 });
    const result = await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" });
    assert.equal(result.permissionDecision, "deny");
    assert.match(result.permissionDecisionReason, /did not become ready/);
});

test("surfaces a stable server startup failure", async () => {
    const session = fakeSession();
    session.rpc.mcp.listConfigured = async () => ({
        servers: [{
            name: "agent-memory-mcp",
            source: "plugin",
            sourcePlugin: "memory-sync",
            enabled: true,
            live: { status: "failed", error: "process exited" },
        }],
    });
    const binding = router(session, { timeoutMs: 5, pollIntervalMs: 1 });
    const result = await binding.preToolUse({ toolName: "agent-memory-mcp-recall_memory" });
    assert.equal(result.permissionDecision, "deny");
    assert.match(result.permissionDecisionReason, /failed: process exited/);
});
