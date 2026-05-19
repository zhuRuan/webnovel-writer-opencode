# 文档中心

`docs/` 目录按功能分区整理，方便查阅。

## 目录索引

### 架构

- [`architecture/overview.md`](./architecture/overview.md)：系统架构、Agent 分工、Story System 设计
- [`architecture/current-system-diagnosis.md`](./architecture/current-system-diagnosis.md)：当前系统状态诊断

### 使用指南

- [`guides/commands.md`](./guides/commands.md)：Skill 命令与 CLI 子命令速查
- [`guides/rag-and-config.md`](./guides/rag-and-config.md)：RAG 检索链路、环境变量与配置
- [`guides/genres.md`](./guides/genres.md)：37 个题材模板与复合题材规则

### 运维

`operations/` 目录中的修复计划均已落地实施，相关文档已随修复完成而归档。当前运维相关命令见 [guides/commands.md](./guides/commands.md) 中的"运维子命令"和"Story System 子命令"章节。

### 记忆系统

- [`memory/long-term-memory-architecture-v2.md`](./memory/long-term-memory-architecture-v2.md)：长期记忆架构说明

### 研究与外部方案

- [`research/long-term-memory-research-report.md`](./research/long-term-memory-research-report.md)：长期记忆论文与开源方案调研
- [`research/storyteller-paper-summary.md`](./research/storyteller-paper-summary.md)：STORYTELLER 论文总结

### Specs

- [`superpowers/README.md`](./superpowers/README.md)：架构 spec 与设计文档导航

## 分类原则

- `architecture/`：系统结构与技术架构
- `guides/`：使用者需要查阅的命令、配置、题材说明
- `memory/`：长期记忆架构说明
- `research/`：论文总结与外部方案调研
- `superpowers/`：架构 spec 与设计文档

## 推荐阅读顺序

1. 先看 [`../README.md`](../README.md) 了解安装与基本使用
2. 再看 [`architecture/overview.md`](./architecture/overview.md) 了解整体架构
3. 需要配置检索时看 [`guides/rag-and-config.md`](./guides/rag-and-config.md)
4. 需要使用命令时看 [`guides/commands.md`](./guides/commands.md)
5. 系统运行健康状态用 `preflight` 和 `status` 命令诊断，详见 [commands.md](./guides/commands.md) 运维子命令
