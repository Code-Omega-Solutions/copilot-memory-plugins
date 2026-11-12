import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const readJson = async (relativePath) =>
    JSON.parse(await readFile(path.join(root, relativePath), "utf8"));

test("memory-sync release versions stay aligned across package and catalog files", async () => {
    const [plugin, marketplace, skill, packageInit] = await Promise.all([
        readJson("plugins/memory-sync/plugin.json"),
        readJson(".github/plugin/marketplace.json"),
        readFile(path.join(root, "plugins/memory-sync/skills/memory-sync/SKILL.md"), "utf8"),
        readFile(path.join(root, "plugins/memory-sync/src/memory_store_sync/__init__.py"), "utf8"),
    ]);
    const pyproject = await readFile(path.join(root, "plugins/memory-sync/pyproject.toml"), "utf8");
    const packageVersion = /^version\s*=\s*"([^"]+)"/m.exec(pyproject)?.[1];
    const cliPackageVersion = /^__version__\s*=\s*"([^"]+)"/m.exec(packageInit)?.[1];
    assert.ok(skill.includes('uvx --from "git+https://github.com/Code-Omega-Solutions/copilot-memory-plugins#subdirectory=plugins/memory-sync" memory-store <command>'));
    const catalogPlugin = marketplace.plugins.find((item) => item.name === "memory-sync");
    const versions = [
        plugin.version,
        packageVersion,
        cliPackageVersion,
        catalogPlugin?.version,
        marketplace.metadata.version,
    ];

    assert.ok(versions.every((version) => typeof version === "string" && /^\d+\.\d+\.\d+$/.test(version)));
    assert.equal(new Set(versions).size, 1, `memory-sync release versions differ: ${versions.join(", ")}`);

    const cliOutput = execFileSync("uv", [
        "tool", "run", "--no-cache", "--isolated", "--from", "./plugins/memory-sync",
        "memory-store", "--version",
    ], { cwd: root, encoding: "utf8", windowsHide: true }).trim();
    assert.equal(cliOutput, `memory-store ${plugin.version}`);
});
