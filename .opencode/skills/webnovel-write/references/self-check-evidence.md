# 修复后自查脚本

审查发现 blocking issue 后，修复阶段使用此脚本检查 evidence 是否仍存在于正文中。

```bash
# 修复后自查：检查上次审查的 evidence 是否仍在正文中
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
# 检查每个 blocking issue 的 evidence 是否仍在正文中
remaining = 0
no_evidence = 0
for issue in blocking:
    evidence = (issue.get('evidence') or '').strip()
    if not evidence:
        no_evidence += 1
        continue
    # evidence 可能是 '原文引用 vs 数据记录' 格式，取 vs 左侧的原文引用部分
    if ' vs ' in evidence:
        evidence = evidence.split(' vs ')[0].strip()
    if len(evidence) >= 3 and evidence[:80] in text:
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
