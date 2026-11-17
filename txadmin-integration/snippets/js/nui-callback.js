// FiveM client JS NUI callback.
RegisterNuiCallbackType('close');
on('__cfx_nui:close', (data, cb) => { SetNuiFocus(false, false); cb({ ok: true }); });
