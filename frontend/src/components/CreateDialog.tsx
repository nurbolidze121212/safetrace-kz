import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { FileSearch, ImagePlus, LoaderCircle, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../lib'
import type { CreateInput, Health } from '../types'
import { Dialog } from './UI'

export default function CreateDialog({ adding, mode: parentMode, caseTitle, health, close, onSubmit }: { adding: boolean; mode?: string; caseTitle?: string; health?: Health; close: () => void; onSubmit: (data: CreateInput) => Promise<void> }) {
  const [text, setText] = useState(''), [url, setUrl] = useState(''), [title, setTitle] = useState(''), [source, setSource] = useState('')
  const [mode, setMode] = useState(parentMode || 'local'), [imageId, setImageId] = useState<string | null>(null)
  const [filename, setFilename] = useState(''), [uploading, setUploading] = useState(false), [sending, setSending] = useState(false), [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const busy = uploading || sending
  async function upload(file?: File) {
    if (!file) return
    setError('')
    if (file.size > 8 * 1024 * 1024) { setError('Изображение должно быть не больше 8 MiB.'); return }
    setUploading(true)
    try {
      const body = new FormData(); body.append('file', file)
      const result = await api<{ image_id: string }>('/uploads', { method: 'POST', body })
      setImageId(result.image_id); setFilename(file.name)
    } catch (e) { setError(errorMessage(e)) } finally { setUploading(false) }
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setSending(true); setError('')
    try { await onSubmit({ title: title.trim() || 'Новый материал', mode, materials: [{ text, url: url.trim(), source: source.trim() || 'Не указан', image_id: imageId }] }) }
    catch (e) { setError(errorMessage(e)) } finally { setSending(false) }
  }
  return <Dialog title={adding ? 'Добавить материал' : 'Новый анализ'} onClose={close} busy={busy}>
    {adding && <p className="dialog-target"><span>Материал для случая</span><strong>{caseTitle}</strong></p>}
    <p className="dialog-intro">Добавьте текст, ссылку или изображение. Система сохранит оригинал и покажет источники каждого вывода.</p>
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        {!adding && <label>Название случая<input data-autofocus value={title} maxLength={180} onChange={e => setTitle(e.target.value)} placeholder="Краткое название для очереди" /></label>}
        <label>Текст публикации<textarea data-autofocus={adding || undefined} aria-label="Текст публикации" aria-describedby="text-length" value={text} maxLength={20000} onChange={e => setText(e.target.value)} placeholder="Исходный текст на русском или казахском…" rows={4} /><span className="field-hint" id="text-length">{text.length.toLocaleString('ru-RU')} / 20 000 символов</span></label>
        <div className="form-grid"><label>URL<input type="url" value={url} maxLength={2048} onChange={e => setUrl(e.target.value)} placeholder="https://…" /></label><label>Заявленный источник<input value={source} maxLength={160} onChange={e => setSource(e.target.value)} placeholder="@аккаунт или название" /></label></div>
        <div className={'upload-area ' + (imageId ? 'has-image' : '')} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void upload(e.dataTransfer.files[0]) }}>
          {imageId ? <><img src={'/api/images/' + imageId} alt="Предпросмотр загруженного изображения" /><div><strong>{filename}</strong><small>Оригинал загружен. Распознавание начнется после отправки.</small><button type="button" className="text-button" onClick={() => { setImageId(null); setFilename('') }}><Trash2 size={15} />Убрать изображение</button></div></> : <><ImagePlus size={28} /><div><button type="button" className="text-button" onClick={() => inputRef.current?.click()}>Загрузить изображение</button><small>Или перетащите сюда · PNG, JPEG, WebP · до 8 MiB / 12 Мп</small></div></>}
          <input ref={inputRef} type="file" hidden accept="image/png,image/jpeg,image/webp" aria-label="Файл изображения" onChange={e => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        </div>
        {!adding && <label>Режим анализа<select value={mode} onChange={e => setMode(e.target.value)}><option value="local">Локальный — OCR и правила</option><option value="synthetic">Синтетический стенд — демонстрационные адреса .test</option><option value="cloud">Облачный контекст — Gemini</option></select></label>}
      </fieldset>
      <p className="field-hint mode-explanation">{mode === 'synthetic' ? 'Собственный безопасный стенд. Результаты помечаются как синтетические.' : mode === 'cloud' ? (health?.provider_available ? 'Текст и изображение будут переданы настроенному Gemini API.' : 'Облачный ключ не настроен. Выполнится локальный анализ с отметкой ограничения.') : health?.offline ? 'Офлайн: настоящий OCR и локальные правила. Внешние страницы недоступны.' : 'Настоящий OCR и локальные правила. Переходы проверяются только для разрешенных доменов.'}</p>
      {error && <div className="alert error" role="alert">{error}</div>}
      <footer className="dialog-actions"><button type="button" onClick={close} disabled={busy}>Отмена</button><button className="primary" type="submit" disabled={busy || !(text.trim() || url.trim() || imageId)}>{busy ? <LoaderCircle className="spin" size={18} /> : <FileSearch size={18} />}{uploading ? 'Загрузка изображения…' : sending ? 'Создание…' : adding ? 'Добавить и проанализировать' : 'Начать анализ'}</button></footer>
    </form>
  </Dialog>
}
