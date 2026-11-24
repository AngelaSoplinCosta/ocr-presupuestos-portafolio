import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ProcessLayout } from './components/ProcessLayout'
import { RouteFocus } from './components/RouteFocus'
import { AppProvider } from './context/AppContext'
import { ColumnsPage } from './pages/ColumnsPage'
import { LocalColumnsPage } from './pages/LocalColumnsPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { HelpPage } from './pages/HelpPage'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProcessingPage } from './pages/ProcessingPage'
import { ResultPage } from './pages/ResultPage'
import { ReviewPage } from './pages/ReviewPage'
import { TemplatesPage } from './pages/TemplatesPage'
import { UploadPage } from './pages/UploadPage'

export function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <RouteFocus />
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="documentos" element={<DocumentsPage />} />
            <Route path="plantillas" element={<TemplatesPage />} />
            <Route path="ayuda" element={<HelpPage />} />
          </Route>
          <Route path="documentos" element={<ProcessLayout />}>
            <Route path="nuevo" element={<UploadPage />} />
            <Route path="nuevo/procesamiento" element={<ProcessingPage />} />
            <Route path="nuevo/columnas" element={<ColumnsPage />} />
            <Route path="local/:jobId/resultado" element={<ResultPage />} />
            <Route path="local/:jobId/revision" element={<ReviewPage />} />
            <Route path="local/:jobId/columnas" element={<LocalColumnsPage />} />
            <Route path="demo/revision" element={<ReviewPage />} />
            <Route path="demo/resultado" element={<ResultPage />} />
          </Route>
          <Route path="*" element={<AppShell />}><Route path="*" element={<NotFoundPage />} /></Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  )
}
