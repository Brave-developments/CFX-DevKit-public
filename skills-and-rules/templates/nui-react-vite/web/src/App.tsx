import { useEffect, useState } from 'react';
export function App() {
  const [visible, setVisible] = useState(false);
  useEffect(() => { const handler = (e: MessageEvent) => { if (e.data?.action === 'visibility') setVisible(Boolean(e.data.visible)); }; window.addEventListener('message', handler); return () => window.removeEventListener('message', handler); }, []);
  async function close() { const getName = (window as any).GetParentResourceName; if (!getName) { setVisible(false); return; } try { await fetch('https://' + getName() + '/close', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); } catch(e) { console.warn(e); } }
  if (!visible) return null;
  return <main style={{background:'#1b1d29',color:'#fff',padding:24,position:'absolute',top:'25%',left:'30%',borderRadius:16}}><h1>CFX React NUI</h1><button onClick={close}>Close</button></main>;
}
