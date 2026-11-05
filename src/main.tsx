import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import 'leaflet/dist/leaflet.css';
import './index.css';
import { hydratePortableState } from './utils/portableState';

void hydratePortableState().finally(() => { createRoot(document.getElementById('root')!).render(<App />); });
