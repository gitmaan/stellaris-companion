import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en/common.json'
import de from './locales/de/common.json'
import fr from './locales/fr/common.json'
import es from './locales/es/common.json'
import ptBR from './locales/pt-BR/common.json'
import ja from './locales/ja/common.json'
import zhHans from './locales/zh-Hans/common.json'
import enXA from './locales/en-XA/common.json'

void i18n.use(initReactI18next).init({
  resources: {
    en: { common: en },
    de: { common: de },
    fr: { common: fr },
    es: { common: es },
    'pt-BR': { common: ptBR },
    ja: { common: ja },
    'zh-Hans': { common: zhHans },
    'en-XA': { common: enXA },
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
