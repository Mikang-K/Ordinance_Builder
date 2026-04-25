import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../types'
import MessageBubble from './MessageBubble'

interface Props {
  messages: ChatMessage[]
  isLoading: boolean
  onOptionSelect?: (value: string) => void
}

export default function ChatWindow({ messages, isLoading, onOptionSelect }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <p>안녕하세요! 만들고 싶은 조례를 자유롭게 말씀해 주세요.</p>
          <p className="hint">예: "서울시 강남구 청년 창업 지원 조례를 만들고 싶습니다"</p>
        </div>
      )}
      {messages.map((msg, i) => (
        <MessageBubble
          key={i}
          message={msg}
          onOptionSelect={onOptionSelect}
          isLastMessage={i === messages.length - 1}
        />
      ))}
      {isLoading && (
        <div className="message-row ai">
          <div className="avatar ai-avatar">AI</div>
          <div className="bubble ai-bubble loading-bubble">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
