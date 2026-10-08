import { useRef } from 'react';
import { X, AlertTriangle } from 'lucide-react';
import { Dialog } from './Dialog';
import { Button } from './Button';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * Accessible replacement for the native window.confirm().
 * Initial focus lands on "Cancel" so the destructive action is never the default.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      labelledBy="confirm-dialog-title"
      initialFocusRef={cancelRef}
      className="max-w-sm"
    >
      <div className="p-5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-4 h-4 text-red-400" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="confirm-dialog-title" className="text-base font-semibold text-primary">
              {title}
            </h2>
            <p className="text-sm text-secondary mt-1">{description}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-auto text-muted hover:text-primary p-1 rounded-md focus-ring"
            aria-label="Cancel"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
        <div className="flex items-center justify-end gap-2 mt-5">
          <Button ref={cancelRef} variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}