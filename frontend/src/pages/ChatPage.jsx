import { useEffect, useState } from 'react'
import { executionApi } from '../api/client'

const LLM_OPTIONS = [
  { value: 'claude', short: 'Claude', label: 'Claude (정확도 높음, 과금)' },
  { value: 'openai', short: 'OpenAI', label: 'OpenAI (과금)' },
  { value: 'ollama', short: 'Ollama', label: 'Ollama (무료, 로컬)' },
]

// 산업용 콘솔 톤(대화 화면은 가볍게): 사이드바 라벨 액센트 바, 선택 항목은 네비 탭과 동일한 액센트 틴트로 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const ACTIVE_TINT = 'rgba(37, 99, 235, 0.08)'
const ACTIVE_BORDER = 'rgba(37, 99, 235, 0.35)'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [provider, setProvider] = useState('claude')
  const [providerMenuOpen, setProviderMenuOpen] = useState(false)
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const currentProvider = LLM_OPTIONS.find((opt) => opt.value === provider) ?? LLM_OPTIONS[0]

  const canSend = input.trim() !== '' && !loading

  const loadSessions = async () => {
    try {
      const res = await executionApi.get('/chat/sessions')
      if (res.data.success) {
        setSessions(res.data.data.sessions)
      }
    } catch {
      // 이력 목록 조회 실패는 채팅 자체를 막지 않음
    }
  }

  useEffect(() => {
    loadSessions()
  }, [])

  const handleNewChat = () => {
    setMessages([])
    setCurrentSessionId(null)
    setError(null)
  }

  const handleSelectSession = async (id) => {
    setError(null)
    try {
      const res = await executionApi.get(`/chat/sessions/${id}`)
      if (res.data.success) {
        setMessages(res.data.data.messages)
        setCurrentSessionId(id)
      } else {
        setError(res.data.message)
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const handleDeleteSession = async (id, e) => {
    e.stopPropagation()
    try {
      await executionApi.delete(`/chat/sessions/${id}`)
      if (id === currentSessionId) {
        handleNewChat()
      }
      await loadSessions()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const handleSend = async () => {
    if (!canSend) return

    const question = input.trim()
    const nextMessages = [...messages, { role: 'user', content: question }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const res = await executionApi.post('/chat', { session_id: currentSessionId, message: question, provider })
      if (res.data.success) {
        setMessages([...nextMessages, { role: 'assistant', content: res.data.data.reply }])
        setCurrentSessionId(res.data.data.session_id)
        loadSessions()
      } else {
        setError(res.data.message)
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <h2>AI 채팅</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        실험 이력, 소재별 현황, 승인된 레시피 등 시스템에 저장된 데이터를 바탕으로 AI에게 질문할 수 있습니다.
      </p>

      <div style={{ display: 'flex', gap: 16, marginTop: 16, alignItems: 'flex-start' }}>
        <div className="card" style={{ width: 220, flexShrink: 0, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleNewChat} style={{ width: '100%' }}>
            + 새 채팅
          </button>
          <div style={{ ...sectionHeadStyle, fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', margin: '4px 0 2px' }}>
            채팅 이력
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto', maxHeight: 440 }}>
            {sessions.length === 0 && (
              <p style={{ color: 'var(--text-muted)', fontSize: 13, padding: '4px 6px' }}>채팅 이력이 없습니다.</p>
            )}
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => handleSelectSession(s.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 4,
                  padding: '8px 10px',
                  borderRadius: 4,
                  cursor: 'pointer',
                  background: s.id === currentSessionId ? ACTIVE_TINT : 'transparent',
                  border: s.id === currentSessionId ? `1px solid ${ACTIVE_BORDER}` : '1px solid transparent',
                }}
              >
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontSize: 13,
                    fontWeight: s.id === currentSessionId ? 700 : 400,
                  }}
                  title={s.title}
                >
                  {s.title || '(제목 없음)'}
                </span>
                <button
                  type="button"
                  onClick={(e) => handleDeleteSession(s.id, e)}
                  title="이 채팅 삭제"
                  style={{ border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0 }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ flex: 1, minHeight: 360, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', maxHeight: 480 }}>
            {messages.length === 0 && (
              <p style={{ color: 'var(--text-muted)' }}>
                예) "M1 10mm + M2 25mm 조합의 OK 비율은?", "최근 실험 결과 요약해줘", "승인된 레시피 알려줘"
              </p>
            )}
            {messages.map((m, idx) => (
              <div
                key={idx}
                style={{
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '80%',
                  background: m.role === 'user' ? 'var(--accent)' : 'var(--bg)',
                  color: m.role === 'user' ? '#fff' : 'var(--text)',
                  border: m.role === 'user' ? 'none' : '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  whiteSpace: 'pre-wrap',
                  lineHeight: 1.6,
                }}
              >
                {m.content}
              </div>
            ))}
            {loading && (
              <div style={{ alignSelf: 'flex-start', color: 'var(--text-muted)' }}>
                <span className="spinner" /> AI 응답 생성 중...
              </div>
            )}
          </div>

          {error && <div className="banner banner-warning" style={{ marginTop: 12 }}>{error}</div>}

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={2}
              placeholder="질문을 입력하세요 (Enter: 전송, Shift+Enter: 줄바꿈)"
              style={{ flex: 1, padding: '8px 10px', border: '1px solid #c7cbd1', borderRadius: 4, resize: 'vertical', fontFamily: 'inherit' }}
            />
            <div style={{ position: 'relative', alignSelf: 'flex-start' }}>
              <button
                type="button"
                className="btn"
                disabled={loading}
                title="응답을 생성할 AI 모델을 선택합니다"
                onClick={() => setProviderMenuOpen((open) => !open)}
                style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}
              >
                {currentProvider.short} ▾
              </button>
              {providerMenuOpen && (
                <div
                  style={{
                    position: 'absolute',
                    bottom: '100%',
                    right: 0,
                    marginBottom: 4,
                    background: '#fff',
                    border: '1px solid var(--border)',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                    borderRadius: 6,
                    zIndex: 10,
                    minWidth: 200,
                  }}
                >
                  {LLM_OPTIONS.map((opt) => (
                    <div
                      key={opt.value}
                      onClick={() => {
                        setProvider(opt.value)
                        setProviderMenuOpen(false)
                      }}
                      style={{
                        padding: '8px 12px',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        fontWeight: opt.value === provider ? 700 : 400,
                        background: opt.value === provider ? 'var(--bg)' : 'transparent',
                      }}
                    >
                      {opt.label}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button className="btn btn-primary" disabled={!canSend} onClick={handleSend} style={{ alignSelf: 'flex-start' }}>
              전송
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
