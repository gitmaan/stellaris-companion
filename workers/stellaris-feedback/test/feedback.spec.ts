import { afterEach, describe, expect, it, vi } from 'vitest'
import worker from '../src/index'

afterEach(() => vi.unstubAllGlobals())

describe('opt-in display diagnostics', () => {
  it.each([false, true])('includes measurements in a report (duplicate=%s)', async duplicate => {
    const sent: Array<{ url: string; body: string }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      sent.push({ url, body: JSON.parse(String(init.body)).body })
      return Response.json({ number: 73, html_url: 'https://github.com/example/example/issues/73' })
    }))
    const query = { bind: vi.fn().mockReturnThis(), first: vi.fn().mockResolvedValue(duplicate ? { github_issue_number: 71, report_count: 1 } : null), run: vi.fn().mockResolvedValue({}) }
    const env = {
      RATE_LIMITS: { get: vi.fn().mockResolvedValue(null), put: vi.fn() },
      DB: { prepare: vi.fn().mockReturnValue(query) },
      GITHUB_TOKEN: 'fixture-token', GITHUB_OWNER: 'example', GITHUB_REPO: 'example',
    } as unknown as Parameters<typeof worker.fetch>[1]
    const response = await worker.fetch(new Request('https://feedback.example/report', {
      method: 'POST', body: JSON.stringify({
        category: 'Missing Content', description: 'Chinese text appears incomplete.',
        context: { appVersion: 'test', platform: 'win32-x64', diagnostics: { display: {
          page: 'chat', language: 'zh-Hans', viewportWidth: 640, viewportHeight: 480,
          windowWidth: 800, windowHeight: 600, zoomFactor: 1.25, displayScaleFactor: 1.5,
          devicePixelRatio: 1.875, privateText: 'must not be included',
        } } },
      }),
    }), env)
    expect(response.status).toBe(200)
    expect(sent).toHaveLength(1)
    expect(sent[0].url.endsWith(duplicate ? '/71/comments' : '/issues')).toBe(true)
    expect(sent[0].body).toContain('### Display diagnostics')
    expect(sent[0].body).toContain('"language": "zh-Hans"')
    expect(sent[0].body).toContain('"displayScaleFactor": 1.5')
    expect(sent[0].body).not.toContain('must not be included')
  })

  it('does not infer diagnostics when the user omits them', async () => {
    const sent = vi.fn().mockResolvedValue(Response.json({ number: 73, html_url: 'https://example.test/73' }))
    vi.stubGlobal('fetch', sent)
    const query = { bind: vi.fn().mockReturnThis(), first: vi.fn().mockResolvedValue(null), run: vi.fn().mockResolvedValue({}) }
    const env = { RATE_LIMITS: { get: vi.fn().mockResolvedValue(null), put: vi.fn() }, DB: { prepare: () => query }, GITHUB_TOKEN: 'fixture', GITHUB_OWNER: 'example', GITHUB_REPO: 'example' } as unknown as Parameters<typeof worker.fetch>[1]
    await worker.fetch(new Request('https://feedback.example/report', { method: 'POST', body: JSON.stringify({ category: 'Bug', description: 'A report', context: { appVersion: 'test', platform: 'win32-x64' } }) }), env)
    expect(JSON.parse(sent.mock.calls[0][1].body).body).not.toContain('Display diagnostics')
  })
})
