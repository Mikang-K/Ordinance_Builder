import type { ChatMessage } from '../types'

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'
  return (
    <div className={`message-row ${isUser ? 'user' : 'ai'}`}>
      {!isUser && <div className="avatar ai-avatar">AI</div>}
      <div className={`bubble ${isUser ? 'user-bubble' : 'ai-bubble'}`}>
        {message.text.split('\n').map((line, i) => (
          <span key={i}>
            {line}
            {i < message.text.split('\n').length - 1 && <br />}
          </span>
        ))}
      </div>
      {isUser && <div className="avatar user-avatar">나</div>}
    </div>
  )
}
