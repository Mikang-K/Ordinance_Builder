export default function LoadingModal({ message }: { message: string }) {
  return (
    <div className="loading-modal-backdrop">
      <div className="loading-modal-card">
        <div className="loading-spinner-wrapper">
          <div className="loading-ring loading-ring-outer" />
          <div className="loading-ring loading-ring-inner" />
          <div className="loading-icon">⚖️</div>
        </div>
        <p className="loading-modal-message">{message}</p>
        <p className="loading-modal-sub">잠시만 기다려 주세요</p>
      </div>
    </div>
  )
}
