import type { LanguageSetting, ResolvedLanguage } from '../hooks/useSettings'

export interface LanguageOption {
  value: LanguageSetting
  label: string
  nativeLabel: string
}

const BASE_LANGUAGE_OPTIONS: LanguageOption[] = [
  { value: 'system', label: 'System default', nativeLabel: 'System default' },
  { value: 'en', label: 'English', nativeLabel: 'English' },
  { value: 'de', label: 'German', nativeLabel: 'Deutsch' },
  { value: 'fr', label: 'French', nativeLabel: 'Francais' },
  { value: 'es', label: 'Spanish', nativeLabel: 'Espanol' },
  { value: 'pt-BR', label: 'Portuguese (Brazil)', nativeLabel: 'Portugues (Brasil)' },
  { value: 'ja', label: 'Japanese', nativeLabel: '日本語' },
  { value: 'zh-Hans', label: 'Simplified Chinese', nativeLabel: '简体中文' },
]

const PSEUDO_LANGUAGE_OPTION: LanguageOption = { value: 'en-XA', label: 'Pseudo', nativeLabel: 'Pseudo' }

export const LANGUAGE_OPTIONS: LanguageOption[] =
  import.meta.env.VITE_SHOW_PSEUDO_LOCALE === 'true'
    ? [...BASE_LANGUAGE_OPTIONS, PSEUDO_LANGUAGE_OPTION]
    : BASE_LANGUAGE_OPTIONS

export const SUPPORTED_RESOLVED_LANGUAGES: ResolvedLanguage[] = [
  'en',
  'de',
  'fr',
  'es',
  'pt-BR',
  'ja',
  'zh-Hans',
  'en-XA',
]

export function isRtlLanguage(_language: string): boolean {
  return false
}
