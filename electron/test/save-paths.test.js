const assert = require('node:assert/strict')
const path = require('node:path')
const test = require('node:test')

const { getLinuxSaveDirCandidates } = require('../main/savePaths')

test('includes native, Flatpak, and common Proton save locations on Linux', () => {
  const homedir = path.join(path.sep, 'home', 'commander')
  const candidates = getLinuxSaveDirCandidates(homedir)
  const protonSuffix = path.join(
    'steamapps',
    'compatdata',
    '281990',
    'pfx',
    'drive_c',
    'users',
    'steamuser',
    'Documents',
    'Paradox Interactive',
    'Stellaris',
    'save games',
  )

  assert.deepEqual(candidates, [
    path.join(homedir, '.local', 'share', 'Paradox Interactive', 'Stellaris', 'save games'),
    path.join(homedir, '.local', 'share', 'Paradox Interactive', 'Stellaris Plaza', 'save games'),
    path.join(
      homedir,
      '.var',
      'app',
      'com.valvesoftware.Steam',
      '.local',
      'share',
      'Paradox Interactive',
      'Stellaris',
      'save games',
    ),
    path.join(homedir, '.steam', 'steam', protonSuffix),
    path.join(homedir, '.local', 'share', 'Steam', protonSuffix),
    path.join(
      homedir,
      '.var',
      'app',
      'com.valvesoftware.Steam',
      'data',
      'Steam',
      protonSuffix,
    ),
  ])
})
