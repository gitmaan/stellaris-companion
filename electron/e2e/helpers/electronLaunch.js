function getElectronLaunchArgs(entrypoint) {
  const args = []
  if (process.env.E2E_NO_SANDBOX === '1') {
    args.push('--no-sandbox')
  }
  args.push(entrypoint)
  return args
}

module.exports = {
  getElectronLaunchArgs,
}
