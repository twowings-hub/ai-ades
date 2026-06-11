import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

const STATUS_PILL = {
  ok: 'pill-ok',
  degraded: 'pill-warn',
  down: 'pill-danger',
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
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          마지막 갱신: {updatedAt.toLocaleTimeString()} (30초마다 자동 갱신)
        </p>
      )}
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>서비스 헬스체크</h3>
        <table>
          <thead>
            <tr>
              <th>서비스</th>
              <th>포트</th>
              <th>상태</th>
              <th>응답시간</th>
            </tr>
          </thead>
          <tbody>
            {(health?.services ?? []).map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td>{s.port}</td>
                <td>
                  <span className={`pill ${STATUS_PILL[s.status] ?? 'pill-muted'}`}>{s.status}</span>
                </td>
                <td>{s.latency_ms != null ? `${s.latency_ms} ms` : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>리소스 사용량</h3>
        {metrics && (
          <>
            <table>
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

            <h3 style={{ marginTop: 20 }}>최근 모델 학습 지표</h3>
            {metrics.model_metrics ? (
              <table>
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
                    <td>{metrics.model_metrics.trained_at}</td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>학습 이력이 없습니다.</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
