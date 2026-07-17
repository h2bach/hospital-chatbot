import * as Dialog from "@radix-ui/react-dialog"
import { LoaderCircle, Trash2, X } from "lucide-react"
import type { SessionSummary } from "../types"

interface ConfirmDeleteDialogProps {
  session: SessionSummary | null
  deleting: boolean
  error: string | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
}

export function ConfirmDeleteDialog({
  session,
  deleting,
  error,
  onOpenChange,
  onConfirm,
}: ConfirmDeleteDialogProps) {
  const title = session?.title.trim() || "Cuộc trò chuyện mới"

  return (
    <Dialog.Root
      open={session !== null}
      onOpenChange={(open) => {
        if (!deleting) onOpenChange(open)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content" aria-describedby="delete-description">
          <div className="dialog-icon danger" aria-hidden="true">
            <Trash2 />
          </div>
          <Dialog.Title>Xóa cuộc trò chuyện?</Dialog.Title>
          <Dialog.Description id="delete-description">
            “{title}” sẽ bị xóa khỏi bộ nhớ máy chủ. Hành động này không thể hoàn tác.
          </Dialog.Description>
          {error ? (
            <div className="inline-alert" role="alert">
              {error}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="secondary-button" disabled={deleting}>
                Hủy
              </button>
            </Dialog.Close>
            <button
              type="button"
              className="danger-button"
              disabled={deleting}
              onClick={onConfirm}
            >
              {deleting ? (
                <LoaderCircle className="spin" aria-hidden="true" />
              ) : (
                <Trash2 aria-hidden="true" />
              )}
              {deleting ? "Đang xóa…" : "Xóa vĩnh viễn"}
            </button>
          </div>
          <Dialog.Close asChild>
            <button
              type="button"
              className="dialog-close icon-button"
              aria-label="Đóng hộp thoại"
              disabled={deleting}
            >
              <X aria-hidden="true" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

