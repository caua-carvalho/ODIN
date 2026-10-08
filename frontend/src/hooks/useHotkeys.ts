import { useEffect } from 'react';

export type HotkeyHandler = (e: KeyboardEvent) => void;
export type HotkeyMap = Record<string, HotkeyHandler>;

const TEXT_INPUT_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return TEXT_INPUT_TAGS.has(target.tagName) || target.isContentEditable;
}

/** True when a modal dialog (native <dialog>) is open, e.g. the command palette. */
export function isModalOpen(): boolean {
  return typeof document !== 'undefined' && document.querySelector('dialog[open]') !== null;
}

/**
 * Normalizes a KeyboardEvent into candidate combo strings.
 * Ctrl/Cmd are normalized to "mod" so the same shortcut works on Mac and Windows/Linux.
 * The bare key is returned as a second candidate so symbols like "?" match with or
 * without the Shift modifier.
 */
function normalizeCombo(e: KeyboardEvent): string[] {
  const parts: string[] = [];
  if (e.ctrlKey || e.metaKey) parts.push('mod');
  if (e.altKey) parts.push('alt');
  if (e.shiftKey) parts.push('shift');
  const rawKey = e.key;
  parts.push(rawKey.length === 1 ? rawKey.toLowerCase() : rawKey);
  return [parts.join('+'), rawKey.toLowerCase()];
}

/**
 * Registers window-level keyboard shortcuts.
 *
 * - Modifier combos (Ctrl/⌘, e.g. "mod+k") always fire.
 * - Escape always fires, so modals and drawers can be dismissed.
 * - Plain keys (letters, digits, "?") are ignored while the user is typing in an
 *   input/textarea or when a modal dialog is open, to avoid hijacking input.
 */
export function useHotkeys(map: HotkeyMap): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const isModCombo = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();

      // Never swallow keys that belong to text input or a modal open on top.
      if (!isModCombo && key !== 'escape') {
        if (isEditableTarget(document.activeElement) || isModalOpen()) return;
      }

      const candidate = normalizeCombo(e);
      for (const combo of candidate) {
        const handler = map[combo];
        if (handler) {
          handler(e);
          return;
        }
      }
    };

    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  });
}