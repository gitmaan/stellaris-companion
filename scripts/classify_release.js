const fs = require('node:fs')

function classifyReleaseVersion(version) {
  if (/^\d+\.\d+\.\d+$/.test(version || '')) {
    return { channel: 'latest', prerelease: false }
  }
  if (/^\d+\.\d+\.\d+-beta\.\d+$/.test(version || '')) {
    return { channel: 'beta', prerelease: true }
  }
  throw new Error(
    `Unsupported release version "${version || ''}". Use X.Y.Z or X.Y.Z-beta.N.`,
  )
}

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

function getReleaseMetadata({ version, tag }) {
  const classification = classifyReleaseVersion(version)
  const expectedTag = `v${version}`
  if (tag && tag !== expectedTag) {
    throw new Error(`Release tag "${tag}" does not match package version "${expectedTag}".`)
  }
  return {
    version,
    tag: expectedTag,
    channel: classification.channel,
    prerelease: classification.prerelease,
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2))
  const metadata = getReleaseMetadata({
    version: args.version,
    tag: args.tag,
  })
  const output = Object.entries(metadata)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n')
  if (args.output) {
    fs.appendFileSync(args.output, `${output}\n`, 'utf8')
  } else {
    process.stdout.write(`${output}\n`)
  }
}

if (require.main === module) {
  try {
    main()
  } catch (error) {
    process.stderr.write(`${error.message}\n`)
    process.exitCode = 1
  }
}

module.exports = {
  classifyReleaseVersion,
  getReleaseMetadata,
  parseArgs,
}
