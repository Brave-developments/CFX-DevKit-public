// FiveM client JavaScript event.
onNet('demo:message', (message) => {
  if (typeof message !== 'string') return;
  console.log(message.slice(0, 200));
});
