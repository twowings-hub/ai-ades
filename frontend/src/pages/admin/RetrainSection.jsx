import { useEffect, useRef, useState } from 'react'
import { executionApi } from '../../api/client'

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바 — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}

export default function RetrainSection() {
  const [status, setStatus] = useState(null)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const pollRef = useRef(null)

  const loadProgress = async () => {
    try {
      const res = await executionApi.get('/admin/model/auto-retrain-progress')
      setProgress(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const startPolling = () => {
    if (pollRef.current) return
    pollRef.current = setInterval(loadStatus, 3000)
  }

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const loadStatus = async () => {
    try {
      const res = await executionApi.get('/admin/model/retrain-status')
      setStatus(res.data.data)
      if (res.data.data.status === 'running') {
        startPolling()
      } else {
        stopPolling()
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    loadStatus()
    loadProgress()
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 재학습이 끝나면(running -> idle) 자동 재학습 진행도도 다시 조회한다
  useEffect(() => {
    if (status?.status === 'idle') {
      loadProgress()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.finished_at])

  const handleRetrain = async () => {
    setStarting(true)
    setError(null)
    try {
      await executionApi.post('/admin/model/retrain', {})
      // 백그라운드로 즉시 시작되므로 상태를 "running"으로 먼저 반영하고 폴링 시작
      setStatus((prev) => ({ ...(prev ?? {}), status: 'running' }))
      startPolling()
      await loadStatus()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div>
      <h2>모델 재학습</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      {progress && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={sectionHeadStyle}>자동 재학습 진행도</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: 8 }}>
            마지막 학습 이후 누적된 실험이 {progress.threshold}건 이상이면 자동으로 재학습이 시작됩니다.
          </p>
          <p>
            누적 {progress.added_since_last_training} / {progress.threshold}건
            {progress.remaining > 0
              ? ` (${progress.remaining}건 더 추가되면 자동 재학습)`
              : ' (조건 충족 — 다음 실험 결과 저장 시 자동 재학습 시작)'}
          </p>
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{
                width: `${Math.min(100, (progress.added_since_last_training / progress.threshold) * 100)}%`,
              }}
            />
          </div>
          <p style={{ color: 'var(--text-muted)', marginTop: 8, fontSize: 13 }}>
            현재 실험 데이터 {progress.current_count}건 / 마지막 학습 시점 {progress.last_trained_count}건
          </p>
        </div>
      )}

      <div className="card">
        <p>
          현재 상태:{' '}
          <span className={`pill ${status?.status === 'running' ? 'pill-warn' : 'pill-ok'}`}>
            {status?.status ?? '-'}
          </span>
        </p>
        {status?.started_at && <p style={{ color: 'var(--text-muted)' }}>시작 시각: {status.started_at}</p>}

        <button
          className="btn btn-primary"
          disabled={starting || status?.status === 'running'}
          onClick={handleRetrain}
        >
          {starting ? <span className="spinner" /> : '재학습 시작'}
        </button>

        {status?.status === 'running' && (
          <p style={{ color: 'var(--text-muted)', marginTop: 12 }}>
            재학습이 진행 중입니다. (Optuna + XGBoost 학습은 수 분 소요될 수 있습니다)
          </p>
        )}

        {status?.status !== 'running' && status?.result === 'success' && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>
            <p>재학습 완료 (종료 시각: {status.finished_at})</p>
            {status.metrics && (
              <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                <li>Kerf R²: {status.metrics.kerf?.r2?.toFixed?.(4) ?? '-'}</li>
                <li>Depth R²: {status.metrics.depth?.r2?.toFixed?.(4) ?? '-'}</li>
                <li>Quality Accuracy: {status.metrics.quality?.accuracy?.toFixed?.(4) ?? '-'}</li>
                <li>Quality F1(OK): {status.metrics.quality?.f1_ok?.toFixed?.(4) ?? '-'}</li>
              </ul>
            )}
          </div>
        )}

        {status?.status !== 'running' && status?.result === 'failed' && (
          <div className="banner banner-warning" style={{ marginTop: 16 }}>
            <p>재학습 실패 (종료 시각: {status.finished_at})</p>
            <p style={{ marginTop: 8 }}>{status.error}</p>
          </div>
        )}
      </div>
    </div>
  )
}
