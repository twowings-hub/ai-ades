import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

// 산업용 콘솔 톤: 입력 각진 모서리 — 타 화면과 통일
const formInputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
}

export default function NotificationsSection() {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/notifications/settings')
      setSettings(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveResult(null)
    setError(null)
    try {
      const res = await executionApi.patch('/admin/notifications/settings', settings)
      setSaveResult(res.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      const res = await executionApi.post('/admin/notifications/test')
      setTestResult(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setTesting(false)
    }
  }

  if (!settings) {
    return (
      <div>
        <h2>알림 설정</h2>
        {error && <div className="banner banner-warning">{error}</div>}
      </div>
    )
  }

  return (
    <div>
      <h2>알림 설정</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 480 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            이메일
            <input
              type="email"
              value={settings.email ?? ''}
              onChange={(e) => handleChange('email', e.target.value)}
              style={formInputStyle}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Slack Webhook URL
            <input
              type="text"
              value={settings.slack_webhook ?? ''}
              onChange={(e) => handleChange('slack_webhook', e.target.value)}
              style={formInputStyle}
            />
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={settings.notify_on_ok}
              onChange={(e) => handleChange('notify_on_ok', e.target.checked)}
            />
            OK 판정 시 알림
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={settings.notify_on_failure}
              onChange={(e) => handleChange('notify_on_failure', e.target.checked)}
            />
            가공 실패(미가공/과가공/NG) 시 알림
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={settings.notify_on_model_degradation}
              onChange={(e) => handleChange('notify_on_model_degradation', e.target.checked)}
            />
            모델 성능 저하 감지 시 알림
          </label>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button className="btn btn-primary" disabled={saving} onClick={handleSave}>
            {saving ? <span className="spinner" /> : '설정 저장'}
          </button>
          <button className="btn" disabled={testing} onClick={handleTest}>
            {testing ? <span className="spinner" /> : '테스트 발송'}
          </button>
        </div>

        {saveResult && <div className="banner banner-success" style={{ marginTop: 16 }}>{saveResult.message}</div>}
        {testResult && (
          <div className="banner banner-info" style={{ marginTop: 16 }}>
            Slack: {testResult.slack} / Email: {testResult.email}
          </div>
        )}
      </div>
    </div>
  )
}
