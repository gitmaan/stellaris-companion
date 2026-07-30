const path = require('path')

const STELLARIS_STEAM_APP_ID = '281990'
const PROTON_SAVE_SEGMENTS = [
  'steamapps',
  'compatdata',
  STELLARIS_STEAM_APP_ID,
  'pfx',
  'drive_c',
  'users',
  'steamuser',
  'Documents',
  'Paradox Interactive',
  'Stellaris',
  'save games',
]

function getLinuxSaveDirCandidates(homedir) {
  const nativeShare = path.join(homedir, '.local', 'share', 'Paradox Interactive')
  const flatpakRoot = path.join(homedir, '.var', 'app', 'com.valvesoftware.Steam')

  return [
    path.join(nativeShare, 'Stellaris', 'save games'),
    path.join(nativeShare, 'Stellaris Plaza', 'save games'),
    path.join(flatpakRoot, '.local', 'share', 'Paradox Interactive', 'Stellaris', 'save games'),
    path.join(homedir, '.steam', 'steam', ...PROTON_SAVE_SEGMENTS),
    path.join(homedir, '.local', 'share', 'Steam', ...PROTON_SAVE_SEGMENTS),
    path.join(flatpakRoot, 'data', 'Steam', ...PROTON_SAVE_SEGMENTS),
  ]
}

module.exports = {
  getLinuxSaveDirCandidates,
}
