# Localization

The desktop app supports English, German, French, Spanish, Brazilian Portuguese, Japanese, and Simplified Chinese. Players can choose a language during setup or in Settings.

## Contributing translations

- Edit the catalogs in `electron/renderer/i18n/locales/<locale>/common.json`; English is the source catalog.
- Translate complete messages and preserve interpolation tokens, product names, and locale-specific plural forms.
- Include labels, accessible names, error messages, native controls, and Chronicle export text when adding a workflow.
- Use `electron/renderer/lib/compositionKey.ts` for Enter and Escape handlers in editable controls so IME composition remains usable.

From `electron/`, regenerate the development pseudo-locale and validate changes:

```sh
npm run localization:pseudo
npm run test:localization
```

Check changed screens at the minimum window size (800 × 600), with enlarged text and longer translations. Review Japanese and Chinese wrapping, and verify exported Chronicle labels when changing export text.
