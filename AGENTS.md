# AGENTS.md

本文件是仓库 AI 协作规则的唯一真源。若与 `CLAUDE.md`、`.github/copilot-instructions.md` 等其他文件冲突，以本文件为准。

## 1. 硬规则

- **目录边界**：后端 `src/`、`data_provider/`、`api/`、`bot/`；Web 前端 `apps/dsa-web/`；桌面端 `apps/dsa-desktop/`；部署 `scripts/`、`.github/workflows/`、`docker/`
- **不擅自提交**：未经明确确认，不执行 `git commit`、`git tag`、`git push`
- **不硬编码**：密钥、账号、路径、模型名、端口、环境差异逻辑一律配置化
- **复用优先**：优先复用现有模块、配置入口、脚本和测试，不新增平行实现
- **配置同步**：新增配置项时必须同步更新 `.env.example` 和相关文档
- **变更记录**：用户可见能力、CLI/API 行为、部署方式、通知方式、报告结构变化时，必须更新 `docs/CHANGELOG.md`

## 2. 构建/测试/检查命令

### Python 后端

```bash
# 安装依赖
pip install -r requirements.txt
pip install flake8 pytest

# 完整 CI gate（推荐）
./scripts/ci_gate.sh

# 分阶段执行
./scripts/ci_gate.sh syntax      # 语法检查
./scripts/ci_gate.sh flake8       # flake8 静态检查
./scripts/ci_gate.sh deterministic # 核心脚本测试
./scripts/ci_gate.sh offline-tests # 离线测试套件

# 运行单个测试（最常用）
python -m pytest tests/test_xxx.py::test_function_name -v

# 按 marker 运行测试
python -m pytest -m "unit" -v           # 快速离线单元测试
python -m pytest -m "integration" -v     # 集成测试（无外网依赖）
python -m pytest -m "not network" -v     # 排除网络测试

# 语法检查单个文件
python -m py_compile path/to/file.py

# flake8 检查（仅严重错误）
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

### Web 前端 (apps/dsa-web)

```bash
cd apps/dsa-web
npm ci
npm run lint          # ESLint 检查
npm run build         # TypeScript + Vite 构建
npm run test          # Vitest 单元测试
npm run test:smoke    # Playwright 端到端测试

# 单个测试文件
npm run test -- tests/xxx.test.ts
```

### 桌面端 (apps/dsa-desktop)

```bash
cd apps/dsa-desktop
npm install
npm run build
```

### 本地功能测试脚本

```bash
./test.sh code        # 股票代码识别测试
./test.sh yfinance     # YFinance 代码转换测试
./test.sh quick        # 快速功能测试
./test.sh syntax      # Python 语法检查
```

## 3. 代码风格指南

### 通用规范

- **语言**：代码注释、docstring、日志文案以清晰准确为准，不强制英文，但应与文件语境保持一致
- **类型**：使用类型提示（Type Hints），复杂函数必须标注参数和返回类型
- **错误处理**：业务逻辑异常使用自定义异常类，避免裸 `except`；API/服务调用必须处理异常并提供有意义的错误信息

### Python 规范

- **格式化**：使用 Black，行长度 120
- **导入排序**：使用 isort，profile=black
- **Linting**：flake8（配置见 `setup.cfg`），忽略 E501、W503、E203、E402
- **命名**：
  - 函数/变量：`snake_case`
  - 类：`PascalCase`
  - 常量：`UPPER_SNAKE_CASE`
  - 私有成员：前缀 `_`
- **Docstring**：函数和类必须添加 docstring，描述参数、返回值和用途
- **类型标注**：
  ```python
  def process_stock(code: str, options: dict[str, Any] | None = None) -> list[dict]:
      """Process stock data."""
  ```

### 前端规范 (apps/dsa-web)

- **语言**：TypeScript
- **Linting**：ESLint + React Hooks 规则
- **格式化**：Prettier（通过 ESLint 集成）
- **测试**：Vitest + React Testing Library
- **E2E**：Playwright

### Git 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: 新功能
fix: Bug 修复
docs: 文档更新
style: 代码格式（不影响功能）
refactor: 重构
perf: 性能优化
test: 测试相关
chore: 构建/工具相关
```

## 4. 验证矩阵

| 检查项 | 来源 | 触发条件 | 是否阻断 |
|--------|------|----------|----------|
| `ai-governance` | CI workflow | AI 协作资产变更 | 是 |
| `backend-gate` | CI workflow | Python 文件变更 | 是 |
| `docker-build` | CI workflow | 任何变更 | 是 |
| `web-gate` | CI workflow | Web 目录变更 | 是（触发时） |
| `network-smoke` | CI workflow | 手动/定时 | 否 |

### 按改动类型执行

- **Python 后端**：运行 `./scripts/ci_gate.sh` 或 `python -m pytest tests/test_xxx.py::test_func`
- **Web 前端**：运行 `npm run lint && npm run build`
- **桌面端**：先构建 Web，再构建桌面端
- **API/Schema 变更**：同时验证后端和受影响客户端

## 5. 稳定性护栏

- **配置变更**：修改 `.env` 语义、默认值、CLI 参数时，评估对本地、Docker、GitHub Actions、Web、Desktop 的影响
- **数据源变更**：`data_provider/` 修改需关注 fallback、字段标准化、缓存、超时策略
- **报告/Prompt 变更**：修改报告结构、`src/services/image_stock_extractor.py` 中 `EXTRACT_PROMPT` 时，在 PR 描述中附完整最新 prompt
- **发布变更**：自动 tag 默认 opt-in，只有 commit title 含 `#patch`、`#minor`、`#major` 才触发版本更新

## 6. 交付结构

每次交付必须包含：

- **改了什么**：具体改动内容
- **为什么这么改**：改动原因和背景
- **验证情况**：本地验证和 CI 结果
- **未验证项**：未覆盖的测试面及原因
- **风险点**：潜在风险和缓解措施
- **回滚方式**：如何回滚本次改动

---

Canonical source for GitHub Copilot: `.github/copilot-instructions.md` 指向本文件。
