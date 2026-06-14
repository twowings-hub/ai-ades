import { useState } from 'react'
import { executionApi } from '../../api/client'

const SERVICES = [
  { name: 'execution-agent', label: 'Execution Agent (8012)', selfRestart: true },
  { name: 'modeling-agent', label: 'Modeling Agent (8011)' },
  { name: 'data-prep-agent', label: 'Data Prep Agent (8010)' },
  { name: 'frontend', label: 'Frontend (5173)' },
  { name: 'influxdb', label: 'InfluxDB (8086)' },
  { name: 'mlflow', label: 'MLflow (5000)' },
  { name: 'grafana', label: 'Grafana (3010)' },
  { name: 'kafka', label: 'Kafka (9092)' },
]

// 산업용 콘솔 톤: 표 데이터 모노스페이스(계기판 느낌) — 타 화면과 통일
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}

export default function ServiceManagementSection() {
  const [loadingService, setLoadingService] = useState(null)
  const [results, setResults] = useState({})

  const handleRestart = async (name) => {
    setLoadingService(name)
    try {
      const res = await executionApi.post(`/admin/services/${name}/restart`)
      setResults((prev) => ({ ...prev, [name]: res.data }))
    } catch (err) {
      setResults((prev) => ({ ...prev, [name]: err.response?.data ?? { success: false, message: err.message } }))
    } finally {
      setLoadingService(null)
    }
  }

  return (
    <div>
      <h2>서비스 관리</h2>
      <div className="card">
        <table className="admin-table" style={readingStyle}>
          <thead>
            <tr>
              <th style={{ width: 220 }}>서비스</th>
              <th style={{ width: 100 }}>작업</th>
              <th style={{ width: 320 }}>결과</th>
            </tr>
          </thead>
          <tbody>
            {SERVICES.map((s) => (
              <tr key={s.name}>
                <td>{s.label}</td>
                <td style={{ textAlign: 'center' }}>
                  <button
                    className="btn btn-sm"
                    disabled={s.selfRestart || loadingService === s.name}
                    onClick={() => handleRestart(s.name)}
                    title={s.selfRestart ? '자기 자신은 재시작할 수 없습니다' : ''}
                  >
                    {loadingService === s.name ? <span className="spinner" /> : '재시작'}
                  </button>
                </td>
                <td>
                  {results[s.name] && (
                    <span style={{ color: results[s.name].success ? 'var(--success)' : 'var(--danger)' }}>
                      {results[s.name].message}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
