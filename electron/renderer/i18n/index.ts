import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import type { ResolvedLanguage } from '../hooks/useSettings'

import en from './locales/en/common.json'

// Every catalog remains packaged locally, including the optional test locale.
// Only English (the fallback) is needed to render the initial application shell.
const catalogLoaders = {
  de: () => import('./locales/de/common.json'),
  fr: () => import('./locales/fr/common.json'),
  es: () => import('./locales/es/common.json'),
  'pt-BR': () => import('./locales/pt-BR/common.json'),
  ja: () => import('./locales/ja/common.json'),
  'zh-Hans': () => import('./locales/zh-Hans/common.json'),
  'en-XA': () => import('./locales/en-XA/common.json'),
}
const pendingCatalogs = new Map<ResolvedLanguage, Promise<void>>()

export async function loadLanguage(language: ResolvedLanguage): Promise<void> {
  if (i18n.hasResourceBundle(language, 'common')) return
  let pending = pendingCatalogs.get(language)
  if (!pending) {
    if (language === 'en') return
    pending = catalogLoaders[language]().then(catalog => {
      i18n.addResourceBundle(language, 'common', catalog.default)
    }).finally(() => {
      // Failed reads can be retried; successful catalogs live in i18next's store.
      pendingCatalogs.delete(language)
    })
    pendingCatalogs.set(language, pending)
  }
  await pending
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { common: en },
  },
  lng: 'en',
  fallbackLng: 'en',
  defaultNS: 'common',
  interpolation: {
    escapeValue: false,
  },
  returnNull: false,
})

export default i18n
