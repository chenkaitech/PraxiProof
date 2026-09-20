# PraxiProof

Compile procedure manuals into executable constraints, verify operation videos against them
with traceable evidence, and package the result as an agent Skill a technician (or an LLM) can
load. Built for the DGX Spark Hackathon.

## 项目简介与核心亮点

PraxiProof 解决的是工业/数据中心运维里一个具体的问题:操作手册是静态文本,但"技术员是否按流程做对了"需要看视频才知道,而人工逐帧核对代价很高。PraxiProof 把这条链路做成了一个可审计的自动化流水线:

1. **手册 → 可执行约束**:用本地 LLM(Ollama 提供)把 PDF/HTML 手册编译成结构化规则(`MUST_HAVE`/`BEFORE`/`AFTER`/`MAX_INTERVAL`/`MUST_NOT`/`COUNT` 等约束类型),每条规则强制携带手册原文引用(页码/章节),不允许模型凭空生成一条没有出处的规则。
2. **视频 → 时间线事件**:提供三种可切换的视频理解后端——`local_vlm`(纯 Ollama 视觉模型,滑窗粗筛+精修两阶段)、`ddm_vlm`(NVIDIA SOP training blueprint 训练的 DDM-Net 边界检测模型做时序切分,再用 VLM 分类,多帧投票降低幻觉)、`nvidia_sop`(直接对接 NVIDIA `sop-monitoring-blueprints` 的 `sop-inference-bp` 推理服务)。三种后端产出统一的 `Observation` 格式,可以直接对比效果。
3. **确定性验证引擎**:规则和观测事件的比对是纯代码逻辑(不是让 LLM"看着办"),每个 verdict(PASS/VIOLATION/UNVERIFIED/INSUFFICIENT_EVIDENCE)都能追溯到具体的手册引用和视频时间段。
4. **Compliance Agent**:一个工具调用型智能体,只能通过 `get_verification_report`/`search_manual`/`inspect_video`/`show_evidence` 等只读工具回答问题,系统提示词明确禁止它自己重新计算时间或推翻已有 verdict——避免"agent 自由发挥"导致的幻觉。
5. **Skill 打包**:把某次验证的结果编译成一份可分发的 Agent Skill(`SKILL.md` + `references/` + `evals/evals.json` + `BENCHMARK.md` + `skill-card.md`),格式对齐 NVIDIA Verified Skills 规范,细节见下文。

核心亮点是**证据链闭环**:从手册引用、视频时间戳、到最终 verdict,每一步都可追溯,拒绝"黑箱裁决"。这也是为什么验证逻辑本身是确定性代码而不是二次调用 LLM——LLM 只负责"看/读","判断规则是否满足"永远是可复现的代码路径。

## 系统架构

```
manual (PDF/HTML)                 video (mp4)
      │                                 │
      ▼                                 ▼
  document/extract.py          video/{local_vlm,ddm_vlm,nvidia_sop}_adapter.py
      │                                 │
      ▼                                 │
  constraints/compiler.py (LLM)         │
      │ RequirementSet                  │ Observation (timed events)
      ▼                                 ▼
      └──────────► constraints/engine.py (deterministic) ─────────┐
                          │ VerificationReport (per-rule verdict)  │
                          ▼                                       │
                  compiler/agent_skill.py ──► SKILL.md + evals.json│
                          │                   + skill-card.md      │
                          ▼                   + BENCHMARK.md       │
                  runtime/compliance_agent.py (tool-calling, read-only)
```

前端是 FastAPI 内置的静态双语(中/英)单页应用(`src/praxiproof/api/static/`),后端 `src/praxiproof/api/app.py` 暴露手册编译、视频上传、一键 pipeline、verdict 复核、Skill 下载、Compliance Agent 问答等 REST 接口。

## 快速开始

```bash
uv sync
uv run praxiproof serve --port 8090        # 启动前后端一体的 Web 服务
uv run praxiproof bench --demo-dir demo    # 在 demo 数据上跑确定性验证引擎的基准测试
uv run pytest -q                           # 单元测试(标记 spark 的用例需要真实 Ollama,默认跳过)
```

## 部署到 DGX Spark

`deploy/deploy.sh` 负责把代码同步到 Spark 并以用户级 systemd service 常驻:

```bash
deploy/deploy.sh                 # rsync 代码 → uv sync → 跑测试 → 重启 praxiproof.service → 健康检查
deploy/deploy.sh --skip-tests    # 跳过测试,加速迭代
```

`deploy/praxiproof.service` 把服务跑在 `0.0.0.0:8090`,通过环境变量指向本地 Ollama(`PRAXIPROOF_OLLAMA_URL=http://127.0.0.1:11434`)。所有可调参数(用哪个 LLM/VLM、用哪个视频后端、DDM 检查点路径、置信度阈值等)既可以用 `PRAXIPROOF_*` 环境变量设置,也可以在跑起来之后通过 `/api/settings` 接口实时热切换(`src/praxiproof/config.py` 的 `EDITABLE` 字段),不需要重启服务——这是"如何优化大模型"这条要求的落点:同一套流水线可以在不同模型间无缝 A/B,把 `praxiproof bench` / `praxiproof eval-sop` 的量化结果作为选型依据,而不是拍脑袋定死一个模型。

`ddm_vlm` 后端的 DDM-Net 边界检测模型跑在独立的 GPU Docker 容器里(`deploy/ddm/Dockerfile`),通过 `PRAXIPROOF_DDM_CHECKPOINT` 指定权重;当前使用的是 NVIDIA SOP training blueprint 提供的通用预训练权重,在自有 demo 录像上做微调(`sop-ddm-finetuning-plugin`/`sop-cr-finetuning-plugin`)是路线图中的下一步。

### LLM/VLM provider:本地 Ollama 或任意 OpenAI 兼容端点

`src/praxiproof/llm.py` 的 `LLM` 是一个只有 `chat`/`chat_json` 两个方法的 Protocol,`OllamaClient` 之外新增了 `OpenAICompatibleClient`——只要是能说 `/v1/chat/completions` 的服务,不管是云端(比如 StepFun 阶跃星辰开放平台 `https://api.stepfun.com/v1`)还是本地起的 OpenAI 兼容服务(vLLM/llama.cpp 等),用的是同一个客户端,区别只在 `base_url`/`api_key`。工具调用(tool_calls)走的就是 OpenAI 原生格式,`ComplianceAgent` 不需要为不同 provider 写分支。

用哪个 provider 由环境变量在启动时决定(和 `ollama_url` 一样是进程级配置,不通过 `/api/settings` 热切换,`api_key` 更是只从环境变量读取、绝不写入 `data/settings.json` 或经 API 暴露):

```bash
export PRAXIPROOF_LLM_PROVIDER=openai        # 默认 ollama
export PRAXIPROOF_OPENAI_BASE_URL=https://api.stepfun.com/v1
export PRAXIPROOF_OPENAI_API_KEY=sk-...
export PRAXIPROOF_LLM_MODEL=step-2-16k       # 换成实际的 StepFun 模型名
```

当前仓库里还没有真实 StepFun API key 去跑通端到端调用,这条链路的正确性靠 `tests/test_llm_openai.py`(mock HTTP 层验证 payload/response 解析)和已有的 `chat`/`chat_json` 消费方(`ComplianceAgent`、`constraints/compiler.py`、视频后端)保证;接入真实 StepFun 模型只需要设置上面三个环境变量,不需要改代码。

## Agent Skills 设计

`compiler/agent_skill.py` 把每次验证结果编译成一份 Skill 包(`demo/sample-skill/dgx-h100-front-fan-module-replacement/` 是一份用 demo 数据生成的真实样例),设计上对齐 NVIDIA Verified Skills 规范的关键项:

- **窄触发、强路由**:`SKILL.md` 的 frontmatter `description` 明确写清楚"什么时候该用这个 skill",而不是把整本手册塞进去。
- **前置证据**:`## Rules that must hold` 每一条都带手册引用,`## Deviations seen in practice` 只列真实观测到的偏差,不臆测。
- **负向用例**:`evals/evals.json` 除了逐条规则生成的正向 case,还固定包含 3 条负向 case(离题问题、引用不存在的规则号、诱导 agent 跳过验证直接下结论),对应 Verified Skills 要求"评测集必须包含'正确答案是不触发'的场景"。
- **Skill Card**:`references/skill-card.md` 记录 Owner、依赖、风险与缓解措施,给人类审查者一个信任记录。
- **BENCHMARK.md**:`compiler/benchmark.py` 把 demo 三段录像(A/B/C)对着人工标注的期望 verdict 跑一遍,映射成 Correctness / Discoverability / Effectiveness / Security / Efficiency 五个维度。当前 Efficiency 和"带 skill / 不带 skill 的 agent 对比"这两项需要连上真实 Ollama 才能测,文档里如实标注为"未测量",不编造数字。

`ComplianceAgent`(`src/praxiproof/runtime/compliance_agent.py`)本身就是这份 Skill 在运行时的体现:它只能通过只读工具查证据,不能自己重新计算或推翻 verdict。

## 技术栈

- **LLM/VLM 推理**:本地 Ollama,或任意 OpenAI 兼容端点(`PRAXIPROOF_LLM_PROVIDER=openai`,见上文),手册编译用 LLM、视频理解用 VLM,模型名可在运行时热切换。
- **NVIDIA 技术栈**:DDM-Net 时序边界检测(来自 `NVIDIA/sop-monitoring-blueprints` 的 training blueprint),GPU 推理容器化部署;`nvidia_sop` 后端预留了对接官方 `sop-inference-bp` 推理服务的接口。
- **Web**:FastAPI + 内置静态双语前端。
- **StepFun 阶跃星辰模型**:通过上面的 OpenAI 兼容 provider 接入——代码/测试已就绪,但本仓库目前没有可用的 StepFun API key 去实跑,还未选定并验证具体模型名(见下文路线图)。

## 已知限制 / Roadmap

- [ ] 用真实 StepFun API key 跑通一次 `PRAXIPROOF_LLM_PROVIDER=openai` 端到端调用,把验证过的模型名(如 `step-2-16k` 之类,以官方最新命名为准)写进本文档和默认配置。
- [ ] 用 `sop-ddm-finetuning-plugin` 在自有 demo 录像上微调 DDM-Net,而不是用通用预训练权重。
- [ ] `BENCHMARK.md` 补上真实 Ollama 环境下的 Efficiency 与"带/不带 skill"对比。
- [ ] 录制 Demo 演示视频、撰写黑客松十日谈征文、补团队合影。
