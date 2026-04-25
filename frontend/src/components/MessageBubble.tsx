import type { ChatMessage } from '../types'

interface Props {
  message: ChatMessage
  onOptionSelect?: (value: string) => void
  isLastMessage?: boolean
}

export default function MessageBubble({ message, onOptionSelect, isLastMessage }: Props) {
  const isUser = message.role === 'user'
  const showChips =
    !isUser &&
    isLastMessage &&
    message.suggested_options &&
    message.suggested_options.length > 0

  return (
    <div className={`message-row ${isUser ? 'user' : 'ai'}`}>
      {!isUser && <div className="avatar ai-avatar">AI</div>}
      <div style={{ display: 'flex', flexDirection: 'column', maxWidth: '80%' }}>
        <div className={`bubble ${isUser ? 'user-bubble' : 'ai-bubble'}`}>
          {(() => {
            const lines = message.text.split('\n')
            return lines.map((line, i) => (
              <span key={i}>
                {line.split('**').map((part, j) => (j % 2 === 1 ? <strong key={j}>{part}</strong> : part))}
                {i < lines.length - 1 && <br />}
              </span>
            ))
          })()}
        </div>
        {showChips && (
          <div className="suggestion-chips">
            {message.suggested_options!.map((opt) => (
              <button
                key={opt.value}
                className="suggestion-chip"
                onClick={() => onOptionSelect?.(opt.value)}
                aria-label={`선택: ${opt.label}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {isUser && <div className="avatar user-avatar">나</div>}
    </div>
  )
}
