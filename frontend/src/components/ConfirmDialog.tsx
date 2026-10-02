import { useEffect, useRef } from "react";
import { X } from "lucide-react";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
};

export function ConfirmDialog({ open, title, description, confirmLabel, danger = false, busy = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel, open]);

  if (!open) return null;

  return (
    <div className="confirmDialogBackdrop" onMouseDown={(event) => { if (event.currentTarget === event.target && !busy) onCancel(); }}>
      <section className="confirmDialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-description">
        <div className="confirmDialogHeader">
          <h2 id="confirm-dialog-title">{title}</h2>
          <button className="modalCloseButton" type="button" onClick={onCancel} disabled={busy} title="取消" aria-label="取消"><X size={17} /></button>
        </div>
        <p id="confirm-dialog-description">{description}</p>
        <div className="confirmDialogActions">
          <button ref={cancelButtonRef} className="secondaryButton" type="button" onClick={onCancel} disabled={busy}>取消</button>
          <button className={danger ? "dangerButton" : "primaryButton"} type="button" onClick={() => void onConfirm()} disabled={busy}>
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
