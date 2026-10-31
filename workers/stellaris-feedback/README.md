# Feedback service ownership

The production `stellaris-feedback` Worker is maintained and deployed only from
[`gitmaan/stellaris-companion-site/workers/stellaris-feedback`](https://github.com/gitmaan/stellaris-companion-site/tree/main/workers/stellaris-feedback).

That implementation owns private surveys, public website reports, desktop reports,
screenshots, and the public feedback board. This repository's older deployable
copy was retired after it overwrote the private survey endpoint (issue #78).

Desktop clients continue to use `https://feedback.galacticfilingcabinet.com/report`.
No desktop update is required for the repair. Change the service, run its contract
tests, and deploy it from the canonical repository; never reintroduce a production
Wrangler configuration here.

See [desktop reporting documentation](../../docs/feedback-reporting.md) for payload
and opt-in privacy details. The service README documents validation and deployment.
