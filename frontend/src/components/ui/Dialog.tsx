import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { cn } from '../../lib/utils';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Accessible name. Prefer labelledBy when the dialog renders its own heading. */
  label?: string;
  labelledBy?: string;
  className?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
}

/**
 * Accessible modal dialog built on the native <dialog> element.
 * The browser provides focus trapping, Escape-to-close and focus return to the
 * trigger element for free; entrance/exit is handled by `dialog.odin-dialog` CSS.
 */
export function Dialog({
  open,
  onClose,
  children,
  label,
  labelledBy,
  className,
  initialFocusRef,
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      if (!dialog.open) dialog.showModal();
      if (initialFocusRef?.current) initialFocusRef.current.focus();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [open, initialFocusRef]);

  return (
    <dialog
      ref={dialogRef}
      aria-label={label}
      aria-labelledby={labelledBy}
      className={cn('odin-dialog', className)}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClose={() => {
        if (dialogRef.current?.open) onClose();
      }}
    >
      {children}
    </dialog>
  );
}