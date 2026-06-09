# 修复后自查脚本

审查发现 blocking issue 后，修复阶段使用此脚本检查 evidence 是否仍存在于正文中。

## 自查逻辑

检查策略：对每个 blocking issue，检查其 evidence 是否仍在正文中。
- 如果 evidence 是精确原文引用（含 `vs` 分隔符），取 `vs` 左侧匹配
- 如果 evidence 是概括性描述，用前 80 字符模糊匹配
- 如果 evidence 为空或过短（<3 字符），视为"无法验证"
- 如果所有 evidence 都已消失，自查通过
- 如果有 evidence 仍存在，自查不通过

**注意**：此自查是启发式的，不能 100% 确认问题已修复。如果自查通过但 reviewer 重审仍发现 blocking，应信任 reviewer 的判断。

```bash
SELF_CHECK_PASSED=$(python -c "
import json, pathlib
chapter_file = pathlib.Path('${CHAPTER_FILE}')
review_file = pathlib.Path('${PROJECT_ROOT}/.webnovel/tmp/review_results.json')
if not chapter_file.exists() or not review_file.exists():
    print('false')
    exit()
text = chapter_file.read_text(encoding='utf-8')
review = json.loads(review_file.read_text(encoding='utf-8'))
issues = review.get('issues', [])
blocking = [i for i in issues if i.get('blocking')]
remaining = 0
no_evidence = 0
for issue in blocking:
    evidence = (issue.get('evidence') or '').strip()
    if not evidence or len(evidence) < 3:
        no_evidence += 1
        continue
    # evidence 可能是 '原文引用 vs 数据记录' 格式，取 vs 左侧的原文引用部分
    if ' vs ' in evidence:
        evidence = evidence.split(' vs ')[0].strip()
    # 归一化后匹配：去除首尾空白，取前 80 字符
    search_str = evidence[:80].strip()
    if len(search_str) >= 3 and search_str in text:
        remaining += 1
# 有 blocking issue 但全部无 evidence（如空正文），自查不通过
if blocking and no_evidence == len(blocking):
    print('false')
# 如果所有 evidence 都已消失，自查通过
elif remaining == 0:
    print('true')
else:
    print('false')
")
```

## 清除 blocking 脚本

用户选择"接受当前版本"时，执行以下脚本清除 blocking：

```bash
python -X utf8 -c "
import json, pathlib
f = pathlib.Path('${PROJECT_ROOT}/.webnovel/tmp/review_results.json')
data = json.loads(f.read_text(encoding='utf-8'))
for issue in data.get('issues', []):
    if isinstance(issue, dict) and issue.get('blocking'):
        issue['blocking'] = False
        issue['severity'] = 'medium'
data['blocking_count'] = 0
f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'已清除 {sum(1 for i in data[\"issues\"] if i.get(\"severity\")==\"medium\")} 个 blocking issue')
"
```
