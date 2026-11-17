const panel = document.getElementById('panel');
window.addEventListener('message', (event) => {
  if (event.data?.action === 'visibility') panel.hidden = !event.data.visible;
});
document.getElementById('close').addEventListener('click', async () => {
  const name = typeof GetParentResourceName === 'function' ? GetParentResourceName() : 'demo';
  if (typeof GetParentResourceName !== 'function') { panel.hidden = true; return; }
  try { await fetch('https://' + name + '/close', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); }
  catch (err) { console.warn('NUI close failed', err); }
});
