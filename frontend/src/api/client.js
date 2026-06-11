import axios from 'axios'

// 각 Agent는 docker-compose에서 호스트로 노출된 포트로 접근한다 (.env 포트 매핑 기준)
export const executionApi = axios.create({ baseURL: 'http://localhost:8012' })
export const modelingApi = axios.create({ baseURL: 'http://localhost:8011' })
export const dataPrepApi = axios.create({ baseURL: 'http://localhost:8010' })
