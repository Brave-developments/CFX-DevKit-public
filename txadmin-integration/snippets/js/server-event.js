// FiveM server JavaScript event. Validate source and ACE before acting.
onNet('demo:request', (resource) => {
  const src = global.source;
  if (!Number.isInteger(src) || src <= 0 || typeof resource !== 'string') return;
  if (!IsPlayerAceAllowed(String(src), 'demo.request')) return;
  console.log('Authorized request');
});
