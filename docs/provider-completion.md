# Provider response completion

Advisor responses include a `completion` object in the local chat API and saved turn metadata. It records the provider finish reason, available token usage, requested output allowance, attempt count, returned text length, and whether recovery succeeded. Missing finish reasons remain `unknown`; punctuation and answer length are not used to guess whether an answer is complete. Old history without this object remains readable.

Native Gemini and OpenAI-compatible Chat Completions adapters own one shared allowance of **two generation calls**. A schema-parameter fallback, schema repair, empty-response repair, quota fallback, or truncation recovery consumes that same allowance. Chronicle does not add another retry around these adapters. Authentication, billing, context-window, blocked-content, and ordinary network failures do not cause speculative retries. Logs record the attempt metadata without prompts, responses, or credentials.

On explicit `MAX_TOKENS` / `length`, the second attempt asks for a concise, complete answer. Application budgets are deliberately below many providers' full limits:

| Selected endpoint/model | Initial default | Recovery ceiling |
| --- | ---: | ---: |
| Native shipped Gemini models (3.8 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite) | 8,192 | 16,384 |
| Official DeepSeek `deepseek-flash`, `deepseek-v4-pro`, legacy `deepseek-reasoner` | 8,192 | 16,384 |
| Official legacy DeepSeek `deepseek-chat` | 8,192 | 8,192 |
| Other models, OpenRouter routes, proxies, or local servers | 4,096 | 4,096 |

DeepSeek recognition requires the exact HTTPS official base URL, `/v1`, or `/beta`, as well as the model ID. A matching model name on another endpoint does not establish its capacity. These are application limits, not promises about remaining context or model availability. Consult the [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models) and [DeepSeek API contract](https://api-docs.deepseek.com/api/create-chat-completion/) when extending the policy. Context-window errors must never trigger a larger output request. Schema-only repairs keep the same allowance.

If both attempts fail to finish, useful unstructured Advisor text is returned as `truncated`. The UI displays a localized notice and retry action, including after reopening a saved conversation. Retrying preserves the old partial answer and sends a new request ID; replaying the previous ID intentionally returns its saved partial. Partial answers stay in the readable archive but are excluded from subsequent completed-turn prompt history. There is no automatic continuation or text stitching.

Chronicle rejects explicit truncation even when the text happens to be valid JSON, so its previous complete content and revision survive failed generation. The separate ChatGPT bridge continues to require `response.completed`; its unknown usage/limits are not fabricated. Its existing schema fallback and one corrective Chronicle call remain bounded by disabling fallback on that corrective call.

Regression coverage uses fake providers and local Electron journeys. It does not spend provider credits. The Chinese layout journey checks every paragraph and exact Copy text in a long virtualized history, three Chromium display scales, three window sizes, and the saved app text-size preference. Windows Actions runs that journey too; a packaged Windows check with native OS scaling and the reporter's actual content remains required before claiming issues #71/#72 are resolved.
