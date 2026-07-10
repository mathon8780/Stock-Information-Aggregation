import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom';
import AppShell from './components/AppShell';
import Dashboard from './pages/Dashboard';
import Market from './pages/Market';
import StockDetail from './pages/StockDetail';
import News from './pages/News';
import Advice from './pages/Advice';
import Settings from './pages/Settings';
import Notifications from './pages/Notifications';
import PaperTrading from './pages/PaperTrading';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'market', element: <Market /> },
      { path: 'stock/:code', element: <StockDetail /> },
      { path: 'news', element: <News /> },
      { path: 'advice', element: <Advice /> },
      { path: 'paper-trading', element: <PaperTrading /> },
      { path: 'paper-admin', element: <Navigate to="/paper-trading" replace /> },
      { path: 'settings', element: <Settings /> },
      { path: 'notifications', element: <Notifications /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
