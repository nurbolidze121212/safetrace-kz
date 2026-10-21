export const analysisComponents = [
  { key: 'rules', label: 'Правила' },
  { key: 'pipeline', label: 'Конвейер' },
  { key: 'ocr', label: 'OCR' },
  { key: 'qr', label: 'QR' },
] as const

function recorded(value: unknown) { return typeof value === 'string' ? value.trim() || undefined : undefined }

export function compareAnalysisVersions(saved?: Record<string, unknown>, running?: Record<string, unknown>) {
  const rows = analysisComponents.map(component => ({
    ...component,
    saved: recorded(saved?.[component.key]),
    running: recorded(running?.[component.key]),
  }))
  const differences = rows.filter(row => row.saved && row.running && row.saved !== row.running)
  const state = differences.length ? 'different' : rows.every(row => row.saved && row.running) ? 'match' : 'unknown'
  return { state, rows, differences }
}
