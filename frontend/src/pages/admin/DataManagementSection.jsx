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

  // 테스트 데이터 정리 (재학습에 반영되지 않은 Auto DOE 실험)
  const [testExperiments, setTestExperiments] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [showConfirm, setShowConfirm] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteResult, setDeleteResult] = useState(null)
  const [deleteError, setDeleteError] = useState(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/data/stats')
      setStats(res.data.data)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const loadTestExperiments = async () => {
    try {
      const res = await executionApi.get('/admin/data/test-experiments')
      setTestExperiments(res.data.data.experiments)
      setSelectedIds([])
    } catch (err) {
      setDeleteError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
    loadTestExperiments()
  }, [])

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id]))
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => (prev.length === testExperiments.length ? [] : testExperiments.map((e) => e.id)))
  }

  const handleDeleteConfirmed = async () => {
    setDeleting(true)
    setDeleteError(null)
    setDeleteResult(null)
    try {
      const res = await executionApi.post('/admin/data/test-experiments/delete', { ids: selectedIds })
      setDeleteResult(res.data)
      setShowConfirm(false)
      setConfirmText('')
      await Promise.all([load(), loadTestExperiments()])
    } catch (err) {
      setDeleteError(err.response?.data?.detail || err.response?.data?.message || err.message)
    } finally {
      setDeleting(false)
    }
  }

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

      <div className="card" style={{ padding: '12px 16px 8px', marginBottom: 0 }}>
        <h3>테이블 현황</h3>
        {stats && (
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: 140 }}>테이블</th>
                <th style={{ width: 100 }}>건수</th>
                <th style={{ width: 160 }}>비고</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>experiments</td>
                <td style={{ textAlign: 'right' }}>{stats.tables.experiments.count}</td>
                <td>이상값 {stats.tables.experiments.outliers}건</td>
              </tr>
              <tr>
                <td>recipes</td>
                <td style={{ textAlign: 'right' }}>{stats.tables.recipes.count}</td>
                <td>-</td>
              </tr>
              <tr>
                <td>approvals</td>
                <td style={{ textAlign: 'right' }}>{stats.tables.approvals.count}</td>
                <td>-</td>
              </tr>
              <tr>
                <td>audit_logs</td>
                <td style={{ textAlign: 'right' }}>{stats.tables.audit_logs.count}</td>
                <td>-</td>
              </tr>
            </tbody>
          </table>
        )}
        <p style={{ color: 'var(--text-muted)', marginTop: 4, marginBottom: 0 }}>
          최근 백업: {stats?.last_backup ?? '없음'}
        </p>
      </div>

      <div className="card" style={{ padding: '4px 16px 12px', marginBottom: 10, marginTop: 4 }}>
        <h3>학습 데이터 업로드</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 8 }}>
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
          <div className="banner banner-warning" style={{ marginTop: 10 }}>{uploadError}</div>
        )}

        {uploadResult && (
          <div className={`banner ${uploadResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginTop: 10 }}>
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
          <div className="banner banner-success" style={{ marginTop: 10 }}>{retrainMessage}</div>
        )}
      </div>

      <div className="card" style={{ padding: '12px 16px', marginBottom: 10 }}>
        <h3>백업 / 내보내기</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" disabled={backing} onClick={handleBackup}>
            {backing ? <span className="spinner" /> : 'DB 백업 (pg_dump)'}
          </button>
          <button className="btn" onClick={handleExport}>experiments CSV 다운로드</button>
        </div>
        {backupResult && (
          <div className={`banner ${backupResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginTop: 10 }}>
            {backupResult.message} {backupResult.data?.filename ?? ''}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: '12px 16px' }}>
        <h3>테스트 데이터 정리</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 8 }}>
          시나리오 테스트 등으로 생성된 Auto DOE 실험 중, <b>아직 재학습에 반영되지 않은</b> 항목만 표시됩니다.
          이미 재학습에 반영된 데이터나 Excel로 업로드된 원본 데이터는 안전을 위해 삭제 대상에서 제외됩니다.
        </p>

        {deleteError && <div className="banner banner-warning" style={{ marginBottom: 8 }}>{deleteError}</div>}
        {deleteResult && (
          <div className={`banner ${deleteResult.success ? 'banner-success' : 'banner-warning'}`} style={{ marginBottom: 8 }}>
            {deleteResult.message}
          </div>
        )}

        {testExperiments.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>정리할 데이터가 없습니다.</p>
        ) : (
          <>
            <div style={{ overflowX: 'auto', maxHeight: 240, overflowY: 'auto' }}>
              <table className="admin-table">
                <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
                  <tr>
                    <th style={{ width: 30, textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selectedIds.length === testExperiments.length}
                        onChange={toggleSelectAll}
                      />
                    </th>
                    <th style={{ width: 120 }}>실험번호</th>
                    <th style={{ width: 220 }}>조건 (speed/defocus/freq/power)</th>
                    <th style={{ width: 150 }}>결과 (kerf/depth)</th>
                    <th style={{ width: 80 }}>판정</th>
                    <th style={{ width: 160 }}>생성 시각</th>
                  </tr>
                </thead>
                <tbody>
                  {testExperiments.map((e) => (
                    <tr key={e.id}>
                      <td style={{ textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(e.id)}
                          onChange={() => toggleSelect(e.id)}
                        />
                      </td>
                      <td>{e.exp_no}</td>
                      <td>{e.speed} / {e.defocus} / {e.frequency} / {e.power}</td>
                      <td>{e.kerf_um} / {e.depth_um}</td>
                      <td>{e.quality}</td>
                      <td>{new Date(e.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <button
              className="btn btn-danger"
              style={{ marginTop: 8 }}
              disabled={selectedIds.length === 0}
              onClick={() => setShowConfirm(true)}
            >
              선택 삭제 ({selectedIds.length}건)
            </button>
          </>
        )}

        {showConfirm && (
          <div className="modal-overlay">
            <div className="modal">
              <h3>테스트 데이터 삭제 확인</h3>
              <p>
                선택한 <b>{selectedIds.length}건</b>의 실험 데이터를 영구 삭제합니다.
                이 작업은 되돌릴 수 없습니다.
              </p>
              <p>계속하려면 아래 입력란에 <b>삭제</b>를 입력하세요.</p>
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                style={{ width: '100%', padding: 8, marginBottom: 16 }}
                placeholder="삭제"
              />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button
                  className="btn"
                  disabled={deleting}
                  onClick={() => {
                    setShowConfirm(false)
                    setConfirmText('')
                  }}
                >
                  취소
                </button>
                <button
                  className="btn btn-danger"
                  disabled={deleting || confirmText !== '삭제'}
                  onClick={handleDeleteConfirmed}
                >
                  {deleting ? <span className="spinner" /> : '영구 삭제'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
