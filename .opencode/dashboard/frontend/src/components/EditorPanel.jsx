import { useCallback, useEffect, useRef, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { oneDark } from '@codemirror/theme-one-dark'
import { saveFileContent, normalizeFile } from '../api.js'

export default function EditorPanel({ path, initialContent, onSave, onCancel, darkMode }) {
    const [content, setContent] = useState(initialContent)
    const [saving, setSaving] = useState(false)
    const [syncing, setSyncing] = useState(false)
    const [msg, setMsg] = useState(null)
    const prevPathRef = useRef(path)

    // 切换文件时重置内容
    useEffect(() => {
        if (prevPathRef.current !== path) {
            prevPathRef.current = path
            setContent(initialContent)
            setMsg(null)
        }
    }, [path, initialContent])

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

    const handleSaveAndSync = useCallback(async () => {
        if (saving || syncing) return
        setSaving(true)
        setMsg(null)
        try {
            await saveFileContent(path, content)
        } catch (e) {
            setMsg({ type: 'error', text: `保存失败: ${e.message}` })
            setSaving(false)
            return
        }

        setSyncing(true)
        try {
            const normResult = await normalizeFile(path)
            if (normResult.changes?.length > 0) {
                setMsg({ type: 'success', text: `已保存并同步 ${normResult.changes.length} 处变更` })
            } else if (normResult.warning) {
                setMsg({ type: 'success', text: `已保存 · ${normResult.warning}` })
            } else {
                setMsg({ type: 'success', text: '已保存' })
            }
        } catch (e) {
            setMsg({ type: 'error', text: `已保存但同步失败: ${e.message}` })
        } finally {
            setSaving(false)
            setSyncing(false)
        }

        onSave?.(content)
        setTimeout(() => setMsg(null), 3000)
    }, [path, content, saving, syncing, onSave])

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
                <button className="page-btn" onClick={handleSave} disabled={saving || syncing}>
                    {saving && !syncing ? '保存中...' : '保存 (Ctrl+S)'}
                </button>
                <button
                    className="page-btn primary"
                    onClick={handleSaveAndSync}
                    disabled={saving || syncing}
                    style={{ marginLeft: 8 }}
                >
                    {syncing ? '同步中...' : '保存并同步'}
                </button>
                <button className="page-btn" onClick={onCancel} disabled={saving || syncing} style={{ background: '#fff8e6' }}>
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
