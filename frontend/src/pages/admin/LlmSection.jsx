import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

export default function LlmSection() {
  const [models, setModels] = useState({ ollama: [], api: {}, current: null })
  const [provider, setProvider] = useState('ollama')
  const [model, setModel] = useState('')
  const [error, setError] = useState(null)
  const [switching, setSwitching] = useState(false)
  const [switchResult, setSwitchResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/llm/available-models')
      setModels(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const currentOptions = provider === 'ollama' ? models.ollama : (models.api?.[provider] ?? [])

  const handleSwitch = async () => {
    setSwitching(true)
    setSwitchResult(null)
    setError(null)
    try {
      const res = await executionApi.post('/admin/llm/switch', { provider, model })
      setSwitchResult(res.data)
      setModels((prev) => ({ ...prev, current: res.data.data }))
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setSwitching(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      const res = await executionApi.post('/admin/llm/test')
      setTestResult(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div>
      <h2>LLM 모델 선택</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      {models.current && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>현재 적용 중인 모델</h3>
          <p style={{ fontSize: 15 }}>
            <strong>{models.current.provider}</strong> / <strong>{models.current.model}</strong>
          </p>
        </div>
      )}

      <div className="card">
        <h3>프로바이더 / 모델 전환</h3>
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            프로바이더
            <select
              value={provider}
              onChange={(e) => { setProvider(e.target.value); setModel('') }}
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 180 }}
            >
              <option value="ollama">ollama</option>
              <option value="claude">claude</option>
              <option value="openai">openai</option>
            </select>
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            모델
            {provider === 'ollama' ? (
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 240 }}
              >
                <option value="">선택하세요</option>
                {models.ollama.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            ) : (
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 240 }}
              >
                <option value="">선택하세요</option>
                {currentOptions.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
          </label>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" disabled={!model || switching} onClick={handleSwitch}>
            {switching ? <span className="spinner" /> : '전환 적용'}
          </button>
          <button className="btn" disabled={testing} onClick={handleTest}>
            {testing ? <span className="spinner" /> : '연결 테스트'}
          </button>
        </div>

        {switchResult && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>
            {switchResult.message} ({switchResult.data.provider} / {switchResult.data.model})
          </div>
        )}

        {testResult && (
          <div className={`banner ${testResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginTop: 16 }}>
            {testResult.success ? '연결 성공' : '연결 실패'} (응답시간: {testResult.latency_ms}ms)
            <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{testResult.response}</div>
          </div>
        )}

        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 16 }}>
          {currentOptions.length === 0 ? '사용 가능한 모델 목록이 비어 있습니다.' : ''}
        </p>
      </div>
    </div>
  )
}
