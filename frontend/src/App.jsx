import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { SessionProvider } from './context/SessionContext'
import ExperimentPage from './pages/ExperimentPage'
import ApprovalPage from './pages/ApprovalPage'
import ResultPage from './pages/ResultPage'
import AdminPage from './pages/AdminPage'
import RecipeSearchPage from './pages/RecipeSearchPage'

function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<ExperimentPage />} />
            <Route path="/approval" element={<ApprovalPage />} />
            <Route path="/result" element={<ResultPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/recipes" element={<RecipeSearchPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  )
}

export default App
