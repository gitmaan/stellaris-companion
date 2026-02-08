const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

// afterPack hook: signs all Mach-O binaries in extraResources
// BEFORE electron-builder signs the main .app, so the seal stays intact.
module.exports = async function afterPack(context) {
  const { electronPlatformName, appOutDir } = context;

  if (electronPlatformName !== "darwin") {
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = path.join(appOutDir, `${appName}.app`);
  const resourcesDir = path.join(appPath, "Contents", "Resources");

  // Resolve the signing identity from the keychain.
  // On CI, electron-builder imports CSC_LINK into a temporary keychain.
  // We find the Developer ID cert hash from whatever keychain is available.
  let identity = process.env.CSC_NAME;
  if (!identity) {
    try {
      const idOutput = execSync(
        'security find-identity -v -p codesigning | grep "Developer ID Application" | head -1',
        { encoding: "utf8" }
      );
      const match = idOutput.match(/([0-9A-F]{40})/);
      identity = match ? match[1] : "Developer ID Application";
      console.log(`afterPack: resolved signing identity: ${identity}`);
    } catch {
      identity = "Developer ID Application";
    }
  }

  console.log(`afterPack: signing bundled binaries in ${resourcesDir}`);

  // Find all Mach-O executables in the Resources directory.
  // `file` output contains "Mach-O" for native binaries.
  let files;
  try {
    files = execSync(
      `find "${resourcesDir}" -type f -exec file {} \\; | grep "Mach-O" | cut -d: -f1`,
      { encoding: "utf8", maxBuffer: 10 * 1024 * 1024 }
    )
      .trim()
      .split("\n")
      .filter(Boolean);
  } catch {
    console.log("afterPack: no Mach-O binaries found in resources, skipping");
    return;
  }

  console.log(`afterPack: found ${files.length} Mach-O binary(ies) to sign`);

  const entitlements = path.join(__dirname, "..", "entitlements.mac.plist");
  const entitlementsArgs = fs.existsSync(entitlements)
    ? `--entitlements "${entitlements}"`
    : "";

  for (const file of files) {
    console.log(`  signing: ${path.relative(appPath, file)}`);
    execSync(
      `codesign --force --options runtime --sign "${identity}" ${entitlementsArgs} "${file}"`,
      { stdio: "inherit" }
    );
  }

  console.log("afterPack: all bundled binaries signed");
};
