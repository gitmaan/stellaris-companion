/** Leave Enter and Escape to an active IME conversion. Chromium can report keyCode 229. */
export function isCompositionKey(event: { isComposing?: boolean; keyCode?: number; nativeEvent?: { isComposing?: boolean; keyCode?: number } }): boolean {
  const native = event.nativeEvent ?? event
  return native.isComposing === true || native.keyCode === 229
}
