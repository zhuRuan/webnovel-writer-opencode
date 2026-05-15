# 插件发版指南

## 版本同步

发版前，先在本地同步 `manifest.json` 和 `README.md` 中的版本号：

```bash
python -X utf8 .opencode/scripts/gen_manifest.py --version X.Y.Z --tag vX.Y.Z --opencode-dir .opencode > manifest.json
```

该命令会自动更新 `manifest.json` 中的版本信息。

## 通过 GitHub Actions 发版

推荐使用 `Version & Release` 工作流统一发版：

1. 手动创建符合 semver 的 Git tag：`git tag vX.Y.Z`
2. 推送 tag：`git push origin vX.Y.Z`
3. 工作流自动执行：
   - `release` job：生成 manifest.json 与 changelog
   - 创建 GitHub Release

## 自动 manifest 更新

`update-manifest` job 在每次 push 到 master 时自动执行，生成日期标记版本号并更新 `manifest.json`。详见 `.github/workflows/manifest.yml`。
