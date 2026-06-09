import { useCallback, useEffect, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { oneDark } from '@codemirror/theme-one-dark'
import { saveFileContent } from '../api.js'

export default function EditorPanel({ path, initialContent, onSave, onCancel, darkMode }) {
    const [content, setContent] = useState(initialContent)
    const [saving, setSaving] = useState(false)
    const [msg, setMsg] = useState(null)

    const charCount = content.length
    const lineCount = content.split(/\n/).length
    const wordCount = content.replace(/\s+/g, '').length

    const handleSave = useCallback(async () => {
        if (saving) return
        setSaving(true)
        setMsg(null)
        try {
            await saveFileContent(path, content)
            setMsg({ type: 'success', text: '保存成功' })
            onSave?.(content)
            setTimeout(() => setMsg(null), 2000)
        } catch (e) {
            setMsg({ type: 'error', text: e.message })
        } finally {
            setSaving(false)
        }
    }, [path, content, saving, onSave])

    useEffect(() => {
        const handler = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault()
                handleSave()
            }
        }
        window.addEventListener('keydown', handler)
        return () => window.removeEventListener('keydown', handler)
    }, [handleSave])

    return (
        <div className="editor-panel">
            <div className="editor-toolbar">
                <button className="page-btn" onClick={handleSave} disabled={saving}>
                    {saving ? '保存中...' : '保存 (Ctrl+S)'}
                </button>
                <button className="page-btn" onClick={onCancel} disabled={saving} style={{ background: '#fff8e6' }}>
                    取消
                </button>
                {msg && (
                    <span style={{
                        color: msg.type === 'error' ? 'var(--accent-red)' : 'var(--accent-green)',
                        fontWeight: 600,
                        fontSize: 13,
                    }}>
                        {msg.text}
                    </span>
                )}
                <span style={{ marginLeft: 'auto', color: 'var(--text-mute)', fontSize: 13 }}>
                    {lineCount} 行 · {wordCount} 字
                </span>
            </div>
            <CodeMirror
                value={content}
                onChange={setContent}
                extensions={[markdown()]}
                theme={darkMode ? oneDark : undefined}
                style={{ border: '2px solid var(--border-main)' }}
                basicSetup={{
                    lineNumbers: true,
                    highlightActiveLine: true,
                    foldGutter: true,
                    bracketMatching: true,
                }}
            />
        </div>
    )
}
