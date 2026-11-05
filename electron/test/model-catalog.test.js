const assert = require('node:assert/strict')
const test = require('node:test')
const cases = require('../../tests/fixtures/model-catalog.json')
const { selectionFamily, stableFamilyModels } = require('../main/modelCatalog')

for (const fixture of cases) {
  test(`shared stable selection: ${fixture.name}`, () => {
    assert.deepEqual(stableFamilyModels(fixture.entries, fixture.provider, fixture.family, '2026-11-02').map(model => model.id), fixture.expected)
  })
}

test('unknown selection families and wrong providers cannot become remote IDs', () => {
  assert.equal(selectionFamily('anthropic/claude-sonnet-5', 'openrouter'), null)
  assert.throws(() => selectionFamily('stellaris:latest-stable/unknown', 'openrouter'))
  assert.throws(() => selectionFamily('stellaris:latest-stable/claude-sonnet', 'custom'))
})
