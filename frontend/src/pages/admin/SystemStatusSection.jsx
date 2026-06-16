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

// 학습 지표 각 항목의 의미 설명 (운영자용 마우스 오버 툴팁 문구)
const METRIC_HELP = {
  kerf_r2:
    '절단 폭(Kerf) 예측 정확도. 0~1이며 1에 가까울수록 정확합니다. (0.9↑ 우수 / 0.7~0.9 양호 / 0.5↓ 점검 필요)',
  depth_r2:
    '절단 깊이(Depth) 예측 정확도. OK 판정(0<Depth≤25μm)의 기준이 되는 핵심 지표로, 이 값이 높아야 AI가 OK 조건을 잘 찾습니다. (0.9↑ 우수)',
  quality_f1_macro:
    'OK/미가공/과가공/NG 4개 판정을 균형 있게 맞히는 점수(각 판정 F1의 평균). 데이터가 적은 판정까지 잘 맞히는지를 보여줘, 불균형 데이터에서는 Accuracy보다 신뢰할 만합니다.',
  quality_accuracy:
    '전체 예측 중 판정을 맞힌 비율. 직관적이지만 특정 판정이 많으면 한쪽으로 쏠려도 높게 나올 수 있습니다.',
  trained_at: '현재 운영 중인 모델이 마지막으로 학습된 시점입니다.',
}

// 항목명 옆에 마우스를 올리면 설명이 뜨는 정보 아이콘 (네이티브 title 툴팁)
const InfoIcon = ({ text }) => (
  <span
    title={text}
    style={{ marginLeft: 5, color: 'var(--text-muted)', cursor: 'help', fontSize: 12 }}
  >
    ⓘ
  </span>
)

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
                      <td>Kerf R²<InfoIcon text={METRIC_HELP.kerf_r2} /></td>
                      <td>{metrics.model_metrics.kerf_r2}</td>
                    </tr>
                    <tr>
                      <td>Depth R²<InfoIcon text={METRIC_HELP.depth_r2} /></td>
                      <td>{metrics.model_metrics.depth_r2}</td>
                    </tr>
                    <tr>
                      <td>Quality F1 (macro)<InfoIcon text={METRIC_HELP.quality_f1_macro} /></td>
                      <td>{metrics.model_metrics.quality_f1_macro}</td>
                    </tr>
                    <tr>
                      <td>Quality Accuracy<InfoIcon text={METRIC_HELP.quality_accuracy} /></td>
                      <td>{metrics.model_metrics.quality_accuracy}</td>
                    </tr>
                    <tr>
                      <td>학습 시각<InfoIcon text={METRIC_HELP.trained_at} /></td>
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
                  {metrics.gpu && (
                    <tr>
                      <td>GPU</td>
                      <td style={readingStyle}>
                        {metrics.gpu.util_percent}% · {metrics.gpu.mem_used_gb} / {metrics.gpu.mem_total_gb} GB · {metrics.gpu.temp_c}°C
                      </td>
                    </tr>
                  )}
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
