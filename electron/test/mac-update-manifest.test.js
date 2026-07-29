const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const { buildMacUpdateManifest } = require('../../scripts/finalize_mac_update_manifest')

test('builds one architecture-complete and OS-gated macOS update manifest', async (t) => {
  const assetsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mac-update-'))
  t.after(() => fs.rmSync(assetsDir, { recursive: true, force: true }))

  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.9.0-arm64-mac.zip'),
    'arm64 archive',
  )
  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.9.0-mac.zip'),
    'x64 archive',
  )

  const manifest = await buildMacUpdateManifest({
    assetsDir,
    minimumSystemVersion: '21.0.0',
    releaseDate: '2026-07-29T12:00:00.000Z',
    releaseNotes: '- Adds model providers.\n- Improves release safety.',
    version: '0.9.0',
  })

  assert.match(manifest, /url: Stellaris-Companion-0\.9\.0-arm64-mac\.zip/)
  assert.match(manifest, /url: Stellaris-Companion-0\.9\.0-mac\.zip/)
  assert.match(manifest, /minimumSystemVersion: 21\.0\.0/)
  assert.match(manifest, /releaseNotes: \|\n  - Adds model providers\./)
  assert.match(manifest, /releaseDate: '2026-07-29T12:00:00\.000Z'/)
})

test('refuses to publish a partial macOS update manifest', async (t) => {
  const assetsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stellaris-mac-update-'))
  t.after(() => fs.rmSync(assetsDir, { recursive: true, force: true }))
  fs.writeFileSync(
    path.join(assetsDir, 'Stellaris-Companion-0.9.0-arm64-mac.zip'),
    'arm64 archive',
  )

  await assert.rejects(buildMacUpdateManifest({
    assetsDir,
    releaseNotes: '- Release note.',
    version: '0.9.0',
  }), /Missing x64 macOS ZIP/)
})
