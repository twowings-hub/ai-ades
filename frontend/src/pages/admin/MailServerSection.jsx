import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 입력 각진 모서리 — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const formInputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
}
const labelStyle = { display: 'flex', flexDirection: 'column', gap: 6 }

export default function MailServerSection() {
  const [form, setForm] = useState(null)
  const [passwordSet, setPasswordSet] = useState(false)
  const [password, setPassword] = useState('') // 빈 값이면 '변경 안 함'
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/notifications/settings')
      const d = res.data.data
      setForm({
        smtp_host: d.smtp_host ?? '',
        smtp_port: d.smtp_port ?? 25,
        smtp_user: d.smtp_user ?? '',
        smtp_from: d.smtp_from ?? '',
        smtp_use_tls: !!d.smtp_use_tls,
      })
      setPasswordSet(!!d.smtp_password_set)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const change = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaving(true)
    setSaveResult(null)
    setError(null)
    try {
      const payload = {
        smtp_host: form.smtp_host.trim() || null,
        smtp_port: Number(form.smtp_port) || 25,
        smtp_user: form.smtp_user.trim() || null,
        smtp_from: form.smtp_from.trim() || null,
        smtp_use_tls: form.smtp_use_tls,
      }
      // 비밀번호는 입력했을 때만 전송한다(빈 값이면 기존 값 유지)
      if (password !== '') payload.smtp_password = password
      const res = await executionApi.patch('/admin/notifications/settings', payload)
      setSaveResult(res.data.message || '저장되었습니다')
      setPassword('')
      await load()
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

  if (!form) {
    return (
      <div>
        <h2>메일 서버 설정</h2>
        {error && <div className="banner banner-warning">{error}</div>}
      </div>
    )
  }

  return (
    <div>
      <h2>메일 서버 설정</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        사내 SMTP 서버를 설정하면 OK/실패 자동 알림과 테스트 메일이 이 서버로 발송됩니다.
        외부 접속이 불가한 폐쇄망에서는 사내(LAN) 메일서버 주소만 사용하세요.
        비워두면 메일은 발송되지 않고 알림은 Grafana 알림판·DB 기록으로만 남습니다.
      </p>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card">
        <h3 style={sectionHeadStyle}>SMTP 서버 접속</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 520 }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <label style={{ ...labelStyle, flex: 1, minWidth: 240 }}>
              호스트 (SMTP_HOST)
              <input
                type="text"
                value={form.smtp_host}
                onChange={(e) => change('smtp_host', e.target.value)}
                placeholder="예: mail.company.local"
                style={formInputStyle}
              />
            </label>
            <label style={{ ...labelStyle, width: 120 }}>
              포트
              <input
                type="number"
                value={form.smtp_port}
                onChange={(e) => change('smtp_port', e.target.value)}
                placeholder="25"
                style={formInputStyle}
              />
            </label>
          </div>

          <label style={labelStyle}>
            사용자 (인증 시, 선택)
            <input
              type="text"
              value={form.smtp_user}
              onChange={(e) => change('smtp_user', e.target.value)}
              placeholder="예: ai-ades"
              style={formInputStyle}
            />
          </label>

          <label style={labelStyle}>
            비밀번호 (인증 시, 선택)
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={passwordSet ? '설정됨 — 변경 시에만 입력' : '미설정'}
              style={formInputStyle}
            />
          </label>

          <label style={labelStyle}>
            발신 주소 (SMTP_FROM)
            <input
              type="text"
              value={form.smtp_from}
              onChange={(e) => change('smtp_from', e.target.value)}
              placeholder="예: ai-ades@company.local"
              style={formInputStyle}
            />
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={form.smtp_use_tls}
              onChange={(e) => change('smtp_use_tls', e.target.checked)}
            />
            STARTTLS 사용
          </label>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
          <button className="btn btn-primary" disabled={saving} onClick={handleSave}>
            {saving ? <span className="spinner" /> : '저장'}
          </button>
          <button className="btn" disabled={testing} onClick={handleTest}>
            {testing ? <span className="spinner" /> : '연결 테스트 (메일 발송)'}
          </button>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          ※ 연결 테스트는 「알림 설정」 화면의 수신 메일 주소로 테스트 메일을 보냅니다. 수신 메일을 먼저 등록하세요.
          DB에 저장된 값이 .env의 SMTP_* 설정보다 우선합니다.
        </p>

        {saveResult && <div className="banner banner-success" style={{ marginTop: 16 }}>{saveResult}</div>}
        {testResult && (
          <div className="banner banner-info" style={{ marginTop: 16 }}>
            메일 발송: {testResult.email}
            {testResult.slack && testResult.slack !== '미설정' ? ` / Slack: ${testResult.slack}` : ''}
          </div>
        )}
      </div>
    </div>
  )
}
