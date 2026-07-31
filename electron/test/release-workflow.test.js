const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  classifyReleaseVersion,
  getReleaseMetadata,
} = require('../../scripts/classify_release')
const {
  buildMacUpdateManifest,
} = require('../../scripts/finalize_mac_update_manifest')

test('classifies stable and beta versions into separate update feeds', () => {
  assert.deepEqual(classifyReleaseVersion('0.8.5'), {
    channel: 'latest',
    prerelease: false,
  })
  assert.deepEqual(classifyReleaseVersion('0.9.0-beta.1'), {
    channel: 'beta',
    prerelease: true,
  })
  assert.throws(() => classifyReleaseVersion('0.9.0-alpha.1'), /Unsupported release version/)
})

test('requires the pushed tag to match the package version exactly', () => {
  assert.deepEqual(getReleaseMetadata({
    version: '0.8.5',
    tag: 'v0.8.5',
  }), {
    version: '0.8.5',
    tag: 'v0.8.5',
    channel: 'latest',
    prerelease: false,
  })
  assert.throws(
    () => getReleaseMetadata({ version: '0.8.5', tag: 'v0.8.6' }),
    /does not match package version/,
  )
})

test('builds one architecture-complete macOS manifest for a stable release', async (t) => {
  const assetsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mac-update-'))
  t.after(() => fs.rmSync(assetsDir, { recursive: true, force: true }))

  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.8.5-arm64-mac.zip'),
    'arm64 archive',
  )
  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.8.5-mac.zip'),
    'x64 archive',
  )

  const manifest = await buildMacUpdateManifest({
    assetsDir,
    releaseDate: '2026-07-30T12:00:00.000Z',
    releaseNotes: '- Publish your Chronicle.',
    version: '0.8.5',
  })

  assert.match(manifest, /url: Stellaris-Companion-0\.8\.5-arm64-mac\.zip/)
  assert.match(manifest, /url: Stellaris-Companion-0\.8\.5-mac\.zip/)
  assert.doesNotMatch(manifest, /minimumSystemVersion/)
  assert.match(manifest, /releaseNotes: \|\n  - Publish your Chronicle\./)
})

test('supports beta asset names and refuses a partial macOS manifest', async (t) => {
  const assetsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mac-update-'))
  t.after(() => fs.rmSync(assetsDir, { recursive: true, force: true }))
  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.9.0-beta.1-arm64-mac.zip'),
    'arm64 archive',
  )

  await assert.rejects(buildMacUpdateManifest({
    assetsDir,
    releaseNotes: '- Provider beta.',
    version: '0.9.0-beta.1',
  }), /Missing x64 macOS ZIP/)
})
