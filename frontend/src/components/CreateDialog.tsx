import { useRef, useState } from 'react'
import type { ClipboardEvent, FormEvent } from 'react'
import { FileSearch, ImagePlus, LoaderCircle, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../lib'
import type { CreateInput, Health } from '../types'
import { Dialog } from './UI'

export default function CreateDialog({ adding, mode: parentMode, caseTitle, health, close, onSubmit }: { adding: boolean; mode?: string; caseTitle?: string; health?: Health; close: () => void; onSubmit: (data: CreateInput) => Promise<void> }) {
  const [text, setText] = useState(''), [url, setUrl] = useState(''), [title, setTitle] = useState(''), [source, setSource] = useState('')
  const [mode, setMode] = useState(parentMode || 'local'), [imageId, setImageId] = useState<string | null>(null)
  const [filename, setFilename] = useState(''), [uploading, setUploading] = useState(false), [sending, setSending] = useState(false), [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const urlRef = useRef<HTMLInputElement>(null)
  const busy = uploading || sending
  async function upload(file?: File) {
    if (!file || busy) return
    setError('')
    if (file.size > 8 * 1024 * 1024) { setError('Изображение должно быть не больше 8 MiB.'); return }
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { setError('Нужен PNG, JPEG или WebP. Для фото HEIC сделайте скриншот или сохраните копию в JPEG.'); return }
    setUploading(true)
    try {
      const body = new FormData(); body.append('file', file)
      const result = await api<{ image_id: string }>('/uploads', { method: 'POST', body })
      setImageId(result.image_id); setFilename(file.name)
    } catch (e) { setError(errorMessage(e)) } finally { setUploading(false) }
  }
  function pasteImage(e: ClipboardEvent<HTMLFormElement>) {
    const file = Array.from(e.clipboardData.items).find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile()
    if (!file) return
    e.preventDefault()
    if (busy) return
    if (imageId) { setError('Изображение уже добавлено. Уберите его, чтобы вставить другое.'); return }
    void upload(file)
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setError('')
    if (url.trim()) {
      try {
        const parsed = new URL(url.trim())
        if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) throw new Error('URL')
      } catch {
        setError('В поле URL нужен полный адрес, начинающийся с http:// или https://.')
        urlRef.current?.focus()
        return
      }
    }
    setSending(true)
    try { await onSubmit({ title: title.trim() || text.trim().replace(/\s+/g, ' ').slice(0, 80) || filename.slice(0, 180) || url.trim().slice(0, 180) || 'Новый материал', mode, materials: [{ text, url: url.trim(), source: source.trim() || 'Не указан', image_id: imageId }] }) }
    catch (e) { setError(errorMessage(e)) } finally { setSending(false) }
  }
  return <Dialog title={adding ? 'Добавить материал' : 'Проверить сообщение'} onClose={close} busy={busy}>
    {adding && <p className="dialog-target"><span>Материал для случая</span><strong>{caseTitle}</strong></p>}
    <p className="dialog-intro">Ищем признаки скрытой рекламы азартных игр. Достаточно текста, ссылки или скриншота — можно добавить всё вместе.</p>
    <form className="message-form" onSubmit={submit} onPaste={pasteImage}>
      <fieldset disabled={busy}>
        <label>Текст сообщения<textarea data-autofocus aria-label="Текст сообщения" aria-describedby="text-length" value={text} maxLength={20000} onChange={e => setText(e.target.value)} placeholder="Скопируйте сообщение целиком, чтобы сохранить контекст…" rows={3} /><span className="field-hint" id="text-length">{text.length.toLocaleString('ru-RU')} / 20 000 · ссылки внутри текста извлекаются автоматически</span></label>
        <label>Ссылка отдельно <span className="optional">· необязательно</span><input ref={urlRef} aria-label="Ссылка" type="url" inputMode="url" autoCapitalize="none" spellCheck={false} value={url} maxLength={2048} onChange={e => setUrl(e.target.value)} placeholder="https://…" /></label>
        <div className={'upload-area ' + (imageId ? 'has-image' : '')} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) void upload(e.dataTransfer.files[0]) }}>
          {imageId ? <><img src={'/api/images/' + imageId} alt="Предпросмотр загруженного изображения" /><div><strong>{filename}</strong><small>Оригинал загружен. Распознавание начнется после отправки.</small><button type="button" className="text-button" onClick={() => { setImageId(null); setFilename(''); setError('') }}><Trash2 size={15} />Убрать изображение</button></div></> : <><ImagePlus size={28} /><div><button type="button" className="text-button" onClick={() => inputRef.current?.click()}>Загрузить скриншот или фото</button><small>Можно вставить из буфера или перетащить файл.<br />PNG, JPEG, WebP · до 8 MiB / 12 Мп</small></div></>}
          <input ref={inputRef} type="file" hidden accept="image/png,image/jpeg,image/webp" aria-label="Файл изображения" onChange={e => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        </div>
        <details className="input-options"><summary>Название, источник и настройки</summary>
          {!adding && <label>Название случая<input value={title} maxLength={180} onChange={e => setTitle(e.target.value)} placeholder="Если пусто — из текста или имени файла" /></label>}
          <label>Заявленный источник<input value={source} maxLength={160} onChange={e => setSource(e.target.value)} placeholder="Например: WhatsApp, группа или канал" /></label>
          {!adding && <label>Режим анализа<select value={mode} onChange={e => setMode(e.target.value)}><option value="local">Локальный — OCR и правила</option><option value="synthetic">Синтетический стенд — демонстрационные адреса .test</option><option value="cloud">Облачный контекст — Gemini</option></select></label>}
        </details>
      </fieldset>
      <p className="field-hint mode-explanation">{mode === 'synthetic' ? 'Собственный безопасный стенд. Результаты помечаются как синтетические.' : mode === 'cloud' ? (health?.provider_available ? 'Текст и изображение будут переданы настроенному Gemini API.' : 'Облачный ключ не настроен. Выполнится локальный анализ с отметкой ограничения.') : health?.offline ? 'Офлайн: настоящий OCR и локальные правила. Внешние страницы недоступны.' : 'Настоящий OCR и локальные правила. Переходы проверяются только для разрешенных доменов.'}</p>
      {error && <div className="alert error" role="alert">{error}</div>}
      <footer className="dialog-actions"><button type="button" onClick={close} disabled={busy}>Отмена</button><button className="primary" type="submit" disabled={busy || !(text.trim() || url.trim() || imageId)}>{busy ? <LoaderCircle className="spin" size={18} /> : <FileSearch size={18} />}{uploading ? 'Загрузка изображения…' : sending ? 'Создание…' : adding ? 'Добавить и проанализировать' : 'Начать анализ'}</button></footer>
    </form>
  </Dialog>
}
