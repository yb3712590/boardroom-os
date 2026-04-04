import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { DashboardPage } from './pages/DashboardPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/review/:reviewPackId" element={<DashboardPage />} />
        <Route path="/incident/:incidentId" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
