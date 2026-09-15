`SKILL.md` is the business authority. Deploy only by fully cloning or copying the complete Skill directory at one fixed Git commit.

## Public command surface

Agents and users must invoke only `scripts/ppa.py`; all other scripts are internal implementation and must not be called as an alternative workflow.

```powershell
# 一次性部署或版本升级；--with-word 仅在确需 Word 时使用
& <python-path> -X utf8 scripts/ppa.py setup [--with-word]

# 创建受控的企业工作区
& <python-path> -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company

# 填写或修订台账后，连续通过所有已满足阶段并停在第一个缺口
& <python-path> -X utf8 scripts/ppa.py advance --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py status --work-dir work/company

# 可选取证和检索仍只通过同一入口
& <python-path> -X utf8 scripts/ppa.py collect-web "企业" "主题" --url <official-url> --out-dir work/company/evidence/topic
& <python-path> -X utf8 scripts/ppa.py collect-equity "企业法律全称" --provider qcc-web --input-json capture.json --out-dir work/company/evidence/qcc
& <python-path> -X utf8 scripts/ppa.py search-catalog "业务关键词" --subject-type domestic
& <python-path> -X utf8 scripts/ppa.py discover-policies --work-dir work/company

# 只有 report_ready 后才可交付；HTML 默认，PDF/Word按需
& <python-path> -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company [--pdf] [--word]
```

- `setup` 优先复用已验证兼容运行时；缺少时才安装项目依赖和项目 Chromium，并完成一次部署验证。日常运行不会重复下载或运行完整测试。
- `start` 创建五份同轮台账和 `workflow-state.json`。不得复制 Flyco fixture 作为新企业底稿。
- 研究人员填充五份台账后，只能通过 `advance` 推进。一次调用会连续通过所有已满足阶段并停在第一个真实缺口；`report_ready` 会写入五份台账哈希，任意文件变更都必须重新完成该阶段。
- `collect-web` 自动校验公开网页证据；`collect-equity` 只归一化用户提供或当前Agent合法访问的企查查/天眼查网页取证；`search-catalog` 按内资/外资路由召回候选；`discover-policies` 只生成非破坏性草案，不覆盖正式台账。
- `deliver` 只接受同一工作区内的五份台账和当前状态回执。缺少能力、证据或实时政策核验时必须停止并说明缺口，不得降级交付。
- 报告修改导致台账哈希变化时，再运行一次 `advance` 重新完成最终门禁；不得手工编辑 `workflow-state.json`。
- 主体确认后，`research-ledger.json.enterprise_profile` 必须标记 `listed / listed_disclosure` 或 `nonlisted / nonlisted_public_evidence`；两条路线只改变来源与停止条件，不改变报告结构或实时政策检索。
