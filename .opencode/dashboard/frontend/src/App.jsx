import { startTransition, useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useOutletContext } from 'react-router-dom'
import { fetchProjectInfo, fetchProjects, switchProject, subscribeSSE } from './api.js'
import {
    BookmarkIcon,
    BookOpenIcon,
    ChartBarIcon,
    ClipboardIcon,
    FileTextIcon,
    FolderIcon,
    LayersIcon,
    PenIcon,
    SlidersIcon,
    TrendingUpIcon,
    UsersIcon,
    WifiIcon,
    WifiOffIcon,
} from './icons.jsx'
const NAV_ITEMS = [
    { to: '/', label: '总览', icon: ChartBarIcon, end: true },
    { to: '/context', label: '上下文健康', icon: LayersIcon },
    { to: '/characters', label: '角色图鉴', icon: UsersIcon },
    { to: '/knowledge', label: '角色知识', icon: BookOpenIcon },
    { to: '/review', label: '审查分析', icon: ClipboardIcon },
    { to: '/pacing', label: '节奏雷达', icon: TrendingUpIcon },
    { to: '/foreshadowing', label: '伏笔追踪', icon: BookmarkIcon },
    { to: '/files', label: '文档浏览', icon: FolderIcon },
    { to: '/style', label: '文风', icon: PenIcon },
    { to: '/trace', label: '执行追踪', icon: FileTextIcon },
    { to: '/process', label: '过程数据', icon: ChartBarIcon },
    { to: '/system', label: '系统状态', icon: SlidersIcon },
]

function ThemeToggle() {
    const [theme, setTheme] = useState(() => {
        try { return localStorage.getItem('theme') || 'light' } catch { return 'light' }
    })

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme)
        try { localStorage.setItem('theme', theme) } catch {}
    }, [theme])

    return (
        <button
            className="theme-toggle"
            onClick={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
            title={theme === 'light' ? '切换到暗色模式' : '切换到亮色模式'}
        >
            {theme === 'light' ? '🌙' : '☀️'}
        </button>
    )
}

export default function App() {
    const [projectInfo, setProjectInfo] = useState(null)
    const [projects, setProjects] = useState([])
    const [currentProjectPath, setCurrentProjectPath] = useState('')
    const [switching, setSwitching] = useState(false)
    const [refreshToken, setRefreshToken] = useState(0)
    const [connected, setConnected] = useState(false)

    const loadProjectInfo = useCallback(() => {
        fetchProjectInfo()
            .then(setProjectInfo)
            .catch(() => setProjectInfo(null))
    }, [])

    const loadProjects = useCallback(() => {
        fetchProjects()
            .then(data => {
                setProjects(data.projects || [])
                setCurrentProjectPath(data.current || '')
            })
            .catch(() => {})
    }, [])

    useEffect(() => {
        loadProjectInfo()
        loadProjects()
    }, [loadProjectInfo, loadProjects, refreshToken])

    useEffect(() => {
        const unsubscribe = subscribeSSE(
            (msg) => {
                startTransition(() => {
                    if (msg && msg.type === 'project-switched') {
                        loadProjects()
                        setSwitching(false)
                    }
                    setRefreshToken(current => current + 1)
                })
            },
            {
                onOpen: () => setConnected(true),
                onError: () => setConnected(false),
            },
        )

        return () => {
            unsubscribe()
            setConnected(false)
        }
    }, [loadProjects])

    const handleSwitchProject = async (path) => {
        if (!path || path === currentProjectPath) return
        setSwitching(true)
        try {
            await switchProject(path)
        } catch (err) {
            console.error('项目切换失败:', err)
            setSwitching(false)
        }
    }

    const title = projectInfo?.project_info?.title || '未加载项目'

    return (
        <div className="app-layout">
            <aside className="sidebar">
                <div className="sidebar-header">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <h1 style={{ margin: 0 }}>PIXEL WRITER HUB</h1>
                        <ThemeToggle />
                    </div>
                    <div className="subtitle" title={title}>{title}</div>
                    {projects.length > 1 && (
                        <div style={{ marginTop: 8 }}>
                            <select
                                value={currentProjectPath}
                                onChange={e => handleSwitchProject(e.target.value)}
                                disabled={switching}
                                style={{
                                    width: '100%',
                                    padding: '4px 6px',
                                    border: '2px solid var(--border-main)',
                                    background: '#fff8e6',
                                    color: 'var(--text-main)',
                                    fontWeight: 600,
                                    fontSize: 11,
                                    fontFamily: 'var(--font-body)',
                                    cursor: 'pointer',
                                }}
                            >
                                {projects.map(p => (
                                    <option key={p.path} value={p.path}>
                                        {p.title}{p.is_current ? ' ✓' : ''}
                                    </option>
                                ))}
                            </select>
                            {switching && (
                                <div style={{ fontSize: 10, color: 'var(--accent-amber)', marginTop: 4, fontWeight: 600 }}>
                                    切换中...
                                </div>
                            )}
                        </div>
                    )}
                </div>
                <nav className="sidebar-nav">
                    {NAV_ITEMS.map(item => {
                        const Icon = item.icon
                        return (
                            <NavLink
                                key={item.to}
                                to={item.to}
                                end={item.end}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`.trim()}
                            >
                                <span className="icon">
                                    <Icon />
                                </span>
                                <span>{item.label}</span>
                            </NavLink>
                        )
                    })}
                </nav>
                <div className="live-indicator">
                    <span className="icon">
                        {connected ? <WifiIcon /> : <WifiOffIcon />}
                    </span>
                    {connected ? '实时同步中' : '实时连接断开'}
                </div>
            </aside>

            <main className="main-content">
                <Outlet context={{ projectInfo, refreshToken, connected, reloadProjectInfo: loadProjectInfo }} />
            </main>
        </div>
    )
}

export function useDashboardContext() {
    return useOutletContext()
}
