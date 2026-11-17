// Browser NUI fetch bridge; use mock behavior outside FiveM for preview.
export async function nuiRequest<T>(event: string, data: object = {}): Promise<T> {
  const root = typeof GetParentResourceName === 'function' ? GetParentResourceName() : 'demo';
  const response = await fetch('https://' + root + '/' + event, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
  });
  if (!response.ok) throw new Error('NUI callback failed: ' + response.status);
  return response.json() as Promise<T>;
}
declare function GetParentResourceName(): string;
