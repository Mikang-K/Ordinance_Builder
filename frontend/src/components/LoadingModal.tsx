export default function LoadingModal({ message }: { message: string }) {
  return (
    <div className="loading-modal-backdrop">
      <div
        className="loading-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="loading-modal-message"
      >
        <div className="loading-spinner-wrapper" aria-hidden="true">
          <div className="loading-ring loading-ring-outer" />
          <div className="loading-ring loading-ring-inner" />
          <div className="loading-icon">⚖️</div>
        </div>
        <p className="loading-modal-message" id="loading-modal-message" role="status" aria-live="polite">{message}</p>
        <p className="loading-modal-sub">잠시만 기다려 주세요</p>
      </div>
    </div>
  )
}
