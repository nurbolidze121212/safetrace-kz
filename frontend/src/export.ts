const connectionError = 'Не удалось получить досье. Проверьте соединение с локальным сервером и повторите экспорт.'

export async function fetchExport(caseId: string, request: typeof fetch = fetch): Promise<Blob> {
  let response: Response
  try { response = await request('/api/cases/' + encodeURIComponent(caseId) + '/export') }
  catch { throw new Error(connectionError) }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Не удалось подготовить досье. Повторите экспорт.')
  }
  if (response.headers.get('content-type')?.split(';')[0] !== 'application/zip') {
    throw new Error('Сервер вернул неожиданный формат вместо ZIP. Досье не скачано.')
  }
  try { return await response.blob() }
  catch { throw new Error(connectionError) }
}
