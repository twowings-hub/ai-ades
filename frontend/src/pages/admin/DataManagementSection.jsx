import { useEffect, useRef, useState } from 'react'
import { dataPrepApi, executionApi } from '../../api/client'

const QUALITY_LABELS = { ok: 'OK', underprocess: '미가공', overprocess: '과가공', ng: 'NG' }

export default function DataManagementSection() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)
  const [backing, setBacking] = useState(false)
  const [backupResult, setBackupResult] = useState(null)

  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [retraining, setRetraining] = useState(false)
  const [retrainMessage, setRetrainMessage] = useState(null)
  const fileInputRef = useRef(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/data/stats')
      setStats(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleBackup = async () => {
    setBacking(true)
    setBackupResult(null)
    setError(null)
    try {
      const res = await executionApi.post('/admin/data/backup')
      setBackupResult(res.data)
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setBacking(false)
    }
  }

  const handleExport = () => {
    window.open(`${executionApi.defaults.baseURL}/admin/data/export`, '_blank')
  }

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    setUploadResult(null)
    setUploadError(null)
    setRetrainMessage(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await dataPrepApi.post('/data/upload', formData)
      setUploadResult(res.data)
      await load()
    } catch (err) {
      setUploadError(err.response?.data?.detail || err.response?.data?.message || err.message)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleRetrain = async () => {
    setRetraining(true)
    setRetrainMessage(null)
    try {
      const res = await executionApi.post('/admin/model/retrain', {})
      setRetrainMessage(res.data.message || '재학습이 시작되었습니다')
    } catch (err) {
      setRetrainMessage(err.response?.data?.message || err.message)
    } finally {
      setRetraining(false)
    }
  }

  return (
    <div>
      <h2>데이터 관리</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>테이블 현황</h3>
        {stats && (
          <table>
            <thead>
              <tr>
                <th>테이블</th>
                <th>건수</th>
                <th>비고</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>experiments</td>
                <td>{stats.tables.experiments.count}</td>
                <td>이상값 {stats.tables.experiments.outliers}건</td>
              </tr>
              <tr>
                <td>recipes</td>
                <td>{stats.tables.recipes.count}</td>
                <td>-</td>
              </tr>
              <tr>
                <td>approvals</td>
                <td>{stats.tables.approvals.count}</td>
                <td>-</td>
              </tr>
              <tr>
                <td>audit_logs</td>
                <td>{stats.tables.audit_logs.count}</td>
                <td>-</td>
              </tr>
            </tbody>
          </table>
        )}
        <p style={{ color: 'var(--text-muted)', marginTop: 12 }}>
          최근 백업: {stats?.last_backup ?? '없음'}
        </p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>학습 데이터 업로드</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 12 }}>
          POC와 동일한 형식(Data 시트 + Sheet1 시트, "No." 행순서 1:1 조인)의 Excel 파일만 업로드하세요.
          기존 No.와 겹치는 행은 자동으로 무시됩니다.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" disabled={uploading} onClick={handleUploadClick}>
            {uploading ? <span className="spinner" /> : 'Excel 업로드'}
          </button>
          {uploadResult && (
            <button className="btn" disabled={retraining} onClick={handleRetrain}>
              {retraining ? <span className="spinner" /> : '재학습 시작'}
            </button>
          )}
        </div>

        {uploadError && (
          <div className="banner banner-warning" style={{ marginTop: 16 }}>{uploadError}</div>
        )}

        {uploadResult && (
          <div className={`banner ${uploadResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginTop: 16 }}>
            <p>{uploadResult.message}</p>
            {uploadResult.data?.distribution && (
              <p style={{ marginTop: 8 }}>
                {Object.entries(uploadResult.data.distribution)
                  .map(([k, v]) => `${QUALITY_LABELS[k] ?? k}: ${v}건`)
                  .join(' / ')}
              </p>
            )}
          </div>
        )}

        {retrainMessage && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>{retrainMessage}</div>
        )}
      </div>

      <div className="card">
        <h3>백업 / 내보내기</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" disabled={backing} onClick={handleBackup}>
            {backing ? <span className="spinner" /> : 'DB 백업 (pg_dump)'}
          </button>
          <button className="btn" onClick={handleExport}>experiments CSV 다운로드</button>
        </div>
        {backupResult && (
          <div className={`banner ${backupResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginTop: 16 }}>
            {backupResult.message} {backupResult.data?.filename ?? ''}
          </div>
        )}
      </div>
    </div>
  )
}
