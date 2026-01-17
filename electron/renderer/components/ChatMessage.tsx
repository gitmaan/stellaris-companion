interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
}

function ChatMessage({ role, content }: ChatMessageProps) {
  return (
    <div className={`chat-message ${role}`}>
      <div className="message-content">{content}</div>
    </div>
  )
}

export default ChatMessage
