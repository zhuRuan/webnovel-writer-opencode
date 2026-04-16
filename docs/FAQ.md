# 常见问题 (FAQ)

遇到问题先查阅本文档，如果无法解决请提交 [Issue](https://github.com/lujih/webnovel-writer-opencode/issues)。

## 目录

- [配置类](#配置类)
- [向量库管理](#向量库管理)
- [项目迁移](#项目迁移)
- [检查器](#检查器)
- [环境问题](#环境问题)

---

## 配置类

### Q: 如何更换 Embedding 模型？

修改项目根目录的 `.env` 文件：

```bash
# 示例：更换为 BAAI/bge-m3
EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
EMBED_MODEL=BAAI/bge-m3
EMBED_API_KEY=your_new_api_key
```

更换后需要重建向量库使新模型生效。详见 [向量库管理](#向量库管理)。

### Q: 如何更换 Rerank 模型？

修改项目根目录的 `.env` 文件：

```bash
# 示例：更换为 bge-reranker-v2-m3
RERANK_BASE_URL=https://api.jina.ai/v1
RERANK_MODEL=bge-reranker-v2-m3
RERANK_API_KEY=your_new_api_key
```

Rerank 模型不需要重建向量库，更换后即时生效。

### Q: API Key 应该在哪里配置？

环境变量加载顺序（优先级从高到低）：

1. 进程环境变量
2. 项目根目录 `.env`
3. 用户级配置 `~/.claude/webnovel-writer/.env`

推荐每本书单独配置 `${项目根}/.env`，避免多项目串配置。

### Q: 如何配置图片生成 API？

修改项目根目录的 `.env` 文件：

```bash
# Image Generation (ModelScope)
IMAGE_BASE_URL=https://api-inference.modelscope.cn/v1
IMAGE_MODEL=Qwen/Qwen-Image-2512
IMAGE_API_KEY=your_modelscope_token
IMAGE_SIZE=1:1
```

获取 API Key：访问 https://modelscope.cn/ → "我的_access_token" → 创建 Token

---

## 向量库管理

### Q: 如何重建单个章节的向量？

```bash
# 重建第 1 章的向量
python .opencode/scripts/webnovel.py rag index-chapter --chapter 1
```

### Q: 如何重建整个向量库？

需要逐章重建，编写脚本遍历所有章节：

```bash
# 遍历章节 1-100 重建
for i in $(seq 1 100); do
    python .opencode/scripts/webnovel.py rag index-chapter --chapter $i
done
```

Windows PowerShell 版本：
```powershell
1..100 | ForEach-Object { python .opencode/scripts/webnovel.py rag index-chapter --chapter $_ }
```

### Q: 如何查看向量库统计信息？

```bash
python .opencode/scripts/webnovel.py rag stats
```

输出包含：向量数量、章节分布、存储大小等。

### Q: 索引重建命令是什么？

```bash
# 重建第 1 章的索引（场景切片 + 向量存储）
python .opencode/scripts/webnovel.py index process-chapter --chapter 1

# 查看索引统计
python .opencode/scripts/webnovel.py index stats
```

### Q: 为什么检索结果不准确？

可能原因：
1. **Embedding 模型未更换** - 更换模型后需重建向量库
2. **向量库为空** - 运行索引重建命令
3. **API Key 无效** - 检查 `.env` 配置

---

## 项目迁移

### Q: 如何将项目迁移到另一台机器？

**步骤：**

1. **复制项目目录**
   ```bash
   # 整个项目目录（包含 .webnovel/）
   rsync -av /path/to/old/project/ /path/to/new/project/
   ```

   Windows:
   ```powershell
   Copy-Item -Recurse -Path "D:\my-novel" -Destination "D:\new-novel"
   ```

2. **在新机器安装**
   ```bash
   python install.py
   ```

3. **配置 API Key**
   编辑新机器上的 `.env` 文件，填入新的 API Key

4. **验证环境**
   ```bash
   python .opencode/scripts/webnovel.py preflight
   ```

### Q: 迁移时需要保留哪些文件？

| 文件/目录 | 是否保留 | 说明 |
|-----------|---------|------|
| `.webnovel/` | ✅ 必须 | 状态数据、索引库 |
| `正文/` | ✅ 必须 | 正文章节 |
| `大纲/` | ✅ 必须 | 章节大纲 |
| `设定集/` | ✅ 必须 | 世界观、角色设定 |
| `.env` | ✅ 必须 | API 配置 |
| `.opencode/` | ❌ 不需要 | 重新运行 `install.py` |

---

## 检查器

### Q: 如何列出所有检查器？

```bash
python .opencode/scripts/webnovel.py checkers list
```

### Q: 如何验证检查器配置？

```bash
python .opencode/scripts/webnovel.py checkers validate
```

### Q: 如何查看特定检查器的 Schema？

```bash
python .opencode/scripts/webnovel.py checkers schema consistency-checker
```

### Q: 如何调试检查器？

1. **查看检查器源码**
   检查器定义在 `.opencode/agents/` 目录下

2. **查看检查器配置**
   配置在 `.opencode/checkers/registry.yaml`

3. **手动运行审查**
   ```bash
   python .opencode/scripts/webnovel.py status --focus all
   ```

4. **启用调试日志**
   ```bash
   # 设置日志级别
   LOG_LEVEL=DEBUG python .opencode/scripts/webnovel.py ...
   ```

### Q: 如何自定义检查器？

详见 [审查器开发指南](./checkers.md)。

---

## 环境问题

### Q: 安装依赖失败怎么办？

```bash
# 升级 pip
python -m pip install --upgrade pip

# 单独安装失败依赖
pip install aiohttp filelock pydantic pytest pytest-asyncio pytest-cov
```

### Q: Windows 下中文路径问题？

确保使用 UTF-8 编码：

```powershell
# 设置终端编码
chcp 65001
set PYTHONIOENCODING=utf-8
```

### Q: 如何查看项目健康状态？

```bash
# Markdown 格式
python .opencode/scripts/webnovel.py status --focus all

# JSON 格式（适合程序处理）
python .opencode/scripts/status_reporter.py --json --pretty --project-root <项目路径>
```

### Q: 如何完全卸载？

```bash
# 删除安装文件
rm -rf .opencode/ .env

# 卸载 Python 依赖
pip uninstall aiohttp filelock pydantic pytest pytest-asyncio pytest-cov -y
```

卸载不会影响你已创建的网文项目文件（正文、大纲、设定集等）。

---

## 相关链接

- [命令详解](./commands.md)
- [RAG 与配置说明](./rag-and-config.md)
- [审查器开发指南](./checkers.md)
- [项目结构与运维](./operations.md)
