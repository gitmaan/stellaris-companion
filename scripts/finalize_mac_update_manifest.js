const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const DEFAULT_MINIMUM_SYSTEM_VERSION = '21.0.0'

function parseArgs(argv) {
  const args = {}
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error(`Invalid argument: ${key || ''}`)
    }
    args[key.slice(2)] = value
  }
  return args
}

function requireFile(filePath, label) {
  let stat
  try {
    stat = fs.statSync(filePath)
  } catch {
    throw new Error(`Missing ${label}: ${filePath}`)
  }
  if (!stat.isFile() || stat.size === 0) {
    throw new Error(`Invalid ${label}: ${filePath}`)
  }
  return stat
}

function sha512Base64(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha512')
    const stream = fs.createReadStream(filePath)
    stream.on('error', reject)
    stream.on('data', chunk => hash.update(chunk))
    stream.on('end', () => resolve(hash.digest('base64')))
  })
}

function indentBlock(value) {
  return value
    .trimEnd()
    .split('\n')
    .map(line => `  ${line}`)
    .join('\n')
}

async function buildMacUpdateManifest({
  assetsDir,
  minimumSystemVersion = DEFAULT_MINIMUM_SYSTEM_VERSION,
  releaseDate,
  releaseNotes,
  version,
}) {
  if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version || '')) {
    throw new Error(`Invalid release version: ${version || ''}`)
  }
  if (!/^\d+(?:\.\d+){1,2}$/.test(minimumSystemVersion || '')) {
    throw new Error(`Invalid minimum system version: ${minimumSystemVersion || ''}`)
  }
  if (!releaseNotes?.trim()) {
    throw new Error('Release notes are required')
  }

  const normalizedDate = releaseDate || new Date().toISOString()
  if (Number.isNaN(Date.parse(normalizedDate))) {
    throw new Error(`Invalid release date: ${normalizedDate}`)
  }

  const assetNames = {
    arm64: `Stellaris-Companion-${version}-arm64-mac.zip`,
    x64: `Stellaris-Companion-${version}-mac.zip`,
  }
  const assets = []
  for (const architecture of ['arm64', 'x64']) {
    const name = assetNames[architecture]
    const filePath = path.join(assetsDir, name)
    const stat = requireFile(filePath, `${architecture} macOS ZIP`)
    assets.push({
      name,
      sha512: await sha512Base64(filePath),
      size: stat.size,
    })
  }

  const x64Asset = assets.find(asset => asset.name === assetNames.x64)
  const fileEntries = assets
    .map(asset => [
      `  - url: ${asset.name}`,
      `    sha512: ${asset.sha512}`,
      `    size: ${asset.size}`,
    ].join('\n'))
    .join('\n')

  return [
    `version: ${version}`,
    'files:',
    fileEntries,
    `path: ${x64Asset.name}`,
    `sha512: ${x64Asset.sha512}`,
    `minimumSystemVersion: ${minimumSystemVersion}`,
    'releaseNotes: |',
    indentBlock(releaseNotes),
    `releaseDate: '${new Date(normalizedDate).toISOString()}'`,
    '',
  ].join('\n')
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const assetsDir = path.resolve(args['assets-dir'] || '')
  const notesPath = path.resolve(args.notes || '')
  const outputPath = path.resolve(args.output || '')
  requireFile(notesPath, 'release notes')

  const manifest = await buildMacUpdateManifest({
    assetsDir,
    minimumSystemVersion: args['minimum-system-version'],
    releaseDate: args['release-date'],
    releaseNotes: fs.readFileSync(notesPath, 'utf8'),
    version: args.version,
  })
  fs.mkdirSync(path.dirname(outputPath), { recursive: true })
  fs.writeFileSync(outputPath, manifest, 'utf8')
  process.stdout.write(`Wrote ${outputPath}\n`)
}

if (require.main === module) {
  main().catch(error => {
    process.stderr.write(`${error.message}\n`)
    process.exitCode = 1
  })
}

module.exports = {
  buildMacUpdateManifest,
  parseArgs,
}
