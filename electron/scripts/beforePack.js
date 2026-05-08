const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

function resolvePythonCommand() {
  const candidates = process.platform === "win32"
    ? [process.env.PYTHON_BIN, "python", "python3"]
    : [process.env.PYTHON_BIN, "python3", "python"];

  for (const candidate of candidates.filter(Boolean)) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (result.status === 0) return candidate;
  }
  throw new Error("beforePack: Python command not found; set PYTHON_BIN or install python3");
}

module.exports = async function beforePack(context) {
  const root = path.resolve(__dirname, "..", "..");
  const backendName = context.electronPlatformName === "win32"
    ? "stellaris-backend.exe"
    : "stellaris-backend";
  const backendPath = path.join(root, "dist-python", "stellaris-backend", backendName);

  if (!fs.existsSync(backendPath)) {
    throw new Error(
      `beforePack: missing bundled backend at ${backendPath}. Run scripts/build-python.sh first.`
    );
  }

  const pythonCommand = resolvePythonCommand();
  const smokeScript = path.join(root, "scripts", "smoke_mcp_stdio.py");
  console.log(`beforePack: verifying bundled MCP backend: ${backendPath}`);
  const result = spawnSync(pythonCommand, [smokeScript, backendPath], {
    cwd: root,
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.status !== 0) {
    throw new Error(
      "beforePack: bundled backend failed MCP smoke verification. "
        + "Run scripts/build-python.sh and try packaging again."
    );
  }
};
