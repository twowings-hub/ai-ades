import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

const STATUS_PILL = {
  ok: 'pill-ok',
  degraded: 'pill-warn',
  down: 'pill-danger',
}

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 표 수치는 모노스페이스(계기판 느낌) — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}

// ISO 타임스탬프를 'YYYY-MM-DD HH:mm' 형태로 단축한다 (초·마이크로초 생략)
const formatShortDateTime = (value) => {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export default function SystemStatusSection() {
  const [health, setHealth] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [updatedAt, setUpdatedAt] = useState(null)

  const load = async () => {
    try {
      const [healthRes, metricsRes] = await Promise.all([
        executionApi.get('/admin/health'),
        executionApi.get('/admin/system-metrics'),
      ])
      setHealth(healthRes.data.data)
      setMetrics(metricsRes.data.data)
      setUpdatedAt(new Date())
      setError(null)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div>
      <h2>시스템 상태</h2>
      {updatedAt && (
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 8 }}>
          마지막 갱신: {updatedAt.toLocaleTimeString()} (30초마다 자동 갱신)
        </p>
      )}
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card" style={{ padding: '12px 16px', marginBottom: 10 }}>
        <h3 style={sectionHeadStyle}>서비스 헬스체크</h3>
        <table className="admin-table" style={readingStyle}>
          <thead>
            <tr>
              <th style={{ width: 200 }}>서비스</th>
              <th style={{ width: 100 }}>포트</th>
              <th style={{ width: 120 }}>상태</th>
              <th style={{ width: 120 }}>응답시간</th>
            </tr>
          </thead>
          <tbody>
            {(health?.services ?? []).map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td>{s.port}</td>
                <td style={{ textAlign: 'center' }}>
                  <span className={`pill ${STATUS_PILL[s.status] ?? 'pill-muted'}`}>{s.status}</span>
                </td>
                <td style={{ textAlign: 'right' }}>{s.latency_ms != null ? `${s.latency_ms} ms` : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ padding: '12px 16px' }}>
        {metrics && (
          <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <div>
              <h3 style={{ ...sectionHeadStyle, marginTop: 0 }}>최근 모델 학습 지표</h3>
              {metrics.model_metrics ? (
                <table className="kv-table kv-table--labels-nowrap" style={readingStyle}>
                  <tbody>
                    <tr>
                      <td>Kerf R²</td>
                      <td>{metrics.model_metrics.kerf_r2}</td>
                    </tr>
                    <tr>
                      <td>Depth R²</td>
                      <td>{metrics.model_metrics.depth_r2}</td>
                    </tr>
                    <tr>
                      <td>Quality F1 (macro)</td>
                      <td>{metrics.model_metrics.quality_f1_macro}</td>
                    </tr>
                    <tr>
                      <td>Quality Accuracy</td>
                      <td>{metrics.model_metrics.quality_accuracy}</td>
                    </tr>
                    <tr>
                      <td>학습 시각</td>
                      <td>{formatShortDateTime(metrics.model_metrics.trained_at)}</td>
                    </tr>
                  </tbody>
                </table>
              ) : (
                <p style={{ color: 'var(--text-muted)' }}>학습 이력이 없습니다.</p>
              )}
            </div>

            <div>
              <h3 style={{ ...sectionHeadStyle, marginTop: 0 }}>리소스 사용량</h3>
              <table className="kv-table">
                <tbody>
                  <tr>
                    <td>CPU</td>
                    <td>{metrics.cpu}%</td>
                  </tr>
                  <tr>
                    <td>RAM</td>
                    <td>{metrics.ram_used_gb} GB / {metrics.ram_total_gb} GB</td>
                  </tr>
                  <tr>
                    <td>Disk</td>
                    <td>{metrics.disk_used_gb} GB / {metrics.disk_total_gb} GB</td>
                  </tr>
                  <tr>
                    <td>LLM</td>
                    <td>{metrics.llm_provider} / {metrics.llm_model}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
