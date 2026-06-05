/**
 * OpenCode Write Guard Plugin
 *
 * 阻止 AI 通过 Write/Edit 工具直接写入受保护的运行时文件。
 * 这些文件只能通过 CLI 命令（webnovel.py chapter-commit 等）写入。
 *
 * 受保护文件：
 * - .webnovel/state.json
 * - .webnovel/index.db
 * - .webnovel/vectors.db
 * - .webnovel/memory_scratchpad.json
 * - .story-system/commits/
 *
 * 禁用方式：设置环境变量 WEBNOVEL_DISABLE_WRITE_GUARD=1
 */

const PROTECTED_SUFFIXES = [
  '.webnovel/state.json',
  '.webnovel/index.db',
  '.webnovel/vectors.db',
  '.webnovel/memory_scratchpad.json',
  '.story-system/commits/',
]

const ALLOWED_MARKERS = [
  'webnovel.py',
  'chapter-commit',
  'write-gate',
  'projections retry',
  'projections replay',
  'chapter_commit_service',
  'state_projection_writer',
  'atomic_write_json',
]

function isProtected(filePath) {
  if (!filePath) return false
  const normalized = filePath.replace(/\\/g, '/').toLowerCase()
  return PROTECTED_SUFFIXES.some(suffix => normalized.includes(suffix))
}

function hasAllowedMarker(command) {
  if (!command) return false
  const lower = command.toLowerCase()
  return ALLOWED_MARKERS.some(marker => lower.includes(marker))
}

export default async function ({ project }) {
  // 环境变量禁用开关
  if (process.env.WEBNOVEL_DISABLE_WRITE_GUARD === '1' ||
      process.env.WEBNOVEL_DISABLE_WRITE_GUARD === 'true') {
    return {}
  }

  return {
    'tool.execute.before': async (input, output) => {
      const tool = input.tool?.toLowerCase()

      // 拦截 Write/Edit 工具
      if (tool === 'write' || tool === 'edit') {
        const path = output.args?.path || output.args?.file_path || ''
        if (isProtected(path)) {
          throw new Error(
            `🚫 禁止直接写入 ${path}。` +
            `这些文件只能通过 CLI 命令写入：\n` +
            `  python webnovel.py chapter-commit\n` +
            `  python webnovel.py state set-chapter-status\n` +
            `如需临时禁用此保护，设置环境变量 WEBNOVEL_DISABLE_WRITE_GUARD=1`
          )
        }
      }

      // 拦截 Bash 工具中的直接文件写入
      if (tool === 'bash') {
        const command = output.args?.command || ''
        // 只检查包含重定向到受保护路径的命令
        if (hasAllowedMarker(command)) return // 白名单放行

        for (const suffix of PROTECTED_SUFFIXES) {
          const normalizedSuffix = suffix.replace(/\\/g, '/').toLowerCase()
          // 检查是否包含受保护路径的写入操作
          if (command.toLowerCase().includes(normalizedSuffix) &&
              (command.includes('>') || command.includes('write') || command.includes('atomic_write'))) {
            throw new Error(
              `🚫 禁止通过 Bash 直接写入 ${suffix}。` +
              `请使用 CLI 命令：python webnovel.py chapter-commit`
            )
          }
        }
      }
    }
  }
}
