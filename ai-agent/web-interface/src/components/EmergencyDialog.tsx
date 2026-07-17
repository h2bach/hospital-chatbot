import * as Dialog from "@radix-ui/react-dialog"
import { PhoneCall, Siren, X } from "lucide-react"

interface EmergencyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EmergencyDialog({ open, onOpenChange }: EmergencyDialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay emergency-overlay" />
        <Dialog.Content
          className="dialog-content emergency-dialog"
          aria-describedby="emergency-description"
        >
          <div className="dialog-icon emergency" aria-hidden="true">
            <Siren />
          </div>
          <p className="dialog-eyebrow">TRƯỜNG HỢP KHẨN CẤP</p>
          <Dialog.Title>Không chờ tư vấn qua chatbot</Dialog.Title>
          <Dialog.Description id="emergency-description">
            Nếu Anh/Chị hoặc người bên cạnh đang đau ngực dữ dội, khó thở, ngất,
            tím tái hoặc không đáp ứng, hãy gọi cấp cứu ngay.
          </Dialog.Description>
          <div className="emergency-steps">
            <strong>Cần làm ngay:</strong>
            <ol>
              <li>Gọi 115 hoặc đến cơ sở cấp cứu gần nhất.</li>
              <li>
                Nếu đang ở Bệnh viện Tim Hà Nội, báo ngay cho nhân viên y tế hoặc đến
                Khoa Cấp cứu.
              </li>
            </ol>
          </div>
          <p className="emergency-disclaimer">
            Trợ lý AI không thể chẩn đoán hay hướng dẫn điều trị trong tình huống khẩn cấp.
          </p>
          <div className="dialog-actions emergency-actions">
            <Dialog.Close asChild>
              <button type="button" className="secondary-button">
                Đóng
              </button>
            </Dialog.Close>
            <a className="emergency-call-button" href="tel:115">
              <PhoneCall aria-hidden="true" />
              Gọi cấp cứu 115
            </a>
          </div>
          <Dialog.Close asChild>
            <button
              type="button"
              className="dialog-close icon-button"
              aria-label="Đóng hướng dẫn khẩn cấp"
            >
              <X aria-hidden="true" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
