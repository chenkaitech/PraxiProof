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

## 两个独立 demo 场景:流水线不是围着一份手册硬编码的

`demo/` 下有两套完全独立的手册+规则+录像,证明这套流水线换一份手册就能重新编译、重新验证,而不是针对某一份 demo 数据写死的脚本:

| | 手册 | 约束类型覆盖 | 生成的 Skill 包 |
|---|---|---|---|
| 场景一 | `demo/manuals/dgx-h100-front-fan-replacement.html` | `PRECONDITION`/`BEFORE`/`AFTER`/`MAX_INTERVAL`/`MUST_HAVE` | `demo/sample-skill/dgx-h100-front-fan-module-replacement/` |
| 场景二 | `demo/manuals/server-fan-psu-cover-installation.md` | `PRECONDITION`/`BEFORE`/**`COUNT`**/`MUST_HAVE`/**`MUST_NOT`** | `demo/sample-skill/server-fan-power-supply-and-cover-installation/` |

场景二特意选了场景一完全没触发过的两种约束——"六个风扇必须都装上"(`COUNT`)和"机盖不能在没听到卡扣声的情况下被强行压下"(`MUST_NOT`),外加一段真实拍到的违规录像(`cover_install_C`:六个风扇和两个电源都装对了,但机盖被强行压下、卡扣没锁上)。跑一下就能看到两条规则同时报 VIOLATION,而且原因各不相同:

```bash
uv run praxiproof bench --demo-dir demo --requirements server-fan-psu-cover.json
```

两个场景各自的 `BENCHMARK.md` 都是用真实数据跑出来的(`praxiproof bench --requirements <file> --skill-md <path>`),不是复制粘贴场景一的数字。`tests/test_benchmark.py` 里有回归测试,保证场景二的录像永远不会被错误地拿场景一的规则去打分。

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
                          │ delegates "why did this fail?" via run_root_cause_analysis
                          ▼
                  runtime/rca_agent.py (separate prompt + raw-data tools)
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

`ddm_vlm` 后端的 DDM-Net 边界检测模型跑在独立的 GPU Docker 容器里(`deploy/ddm/Dockerfile`),通过 `PRAXIPROOF_DDM_CHECKPOINT` 指定权重。线上 Spark 用的是**我们在 Spark 上自己微调的权重**(训练配置和脚本见 `deploy/ddm/train/`,实验数据见下文"模型调优与消融实验"),不是通用预训练权重。

### LLM/VLM provider:本地 Ollama 或任意 OpenAI 兼容端点

`src/praxiproof/llm.py` 的 `LLM` 是一个只有 `chat`/`chat_json` 两个方法的 Protocol,`OllamaClient` 之外新增了 `OpenAICompatibleClient`——只要是能说 `/v1/chat/completions` 的服务,不管是云端(比如 StepFun 阶跃星辰开放平台 `https://api.stepfun.com/v1`)还是本地起的 OpenAI 兼容服务(vLLM/llama.cpp 等),用的是同一个客户端,区别只在 `base_url`/`api_key`。工具调用(tool_calls)走的就是 OpenAI 原生格式,`ComplianceAgent` 不需要为不同 provider 写分支。

用哪个 provider 由环境变量在启动时决定(和 `ollama_url` 一样是进程级配置,不通过 `/api/settings` 热切换,`api_key` 更是只从环境变量读取、绝不写入 `data/settings.json` 或经 API 暴露):

```bash
export PRAXIPROOF_LLM_PROVIDER=openai        # 默认 ollama
export PRAXIPROOF_OPENAI_BASE_URL=https://api.stepfun.com/v1
export PRAXIPROOF_OPENAI_API_KEY=sk-...
export PRAXIPROOF_LLM_MODEL=step-3.5-flash   # 实测可用,见下
```

已用 StepFun 阶跃星辰的真实 API 端到端验证过(2026-09-21,`base_url` 为 `https://api.stepfun.com/step_plan/v1`):`chat_json`(`json_schema` 严格模式)、工具调用、手册编译、验证、Agent 追问(含委托 RCA agent,中英文)全部跑通。原始数据见 `docs/eval/stepfun_compile_benchmark.json`。几点实测结论:

- **模型选择**:编译同一份手册,`step-router-v1` 42 秒/15 条规则,`step-3.5-flash` 94 秒/17 条,`step-3.7-flash` 78 秒但只有 3 条规则(其他几次是 13、15 条),`step-5-preview` 超时 600 秒;本地 `qwen3.6:35b` 在 Spark 上 190 秒/15 条。端到端验证用的是 `step-3.5-flash`(15 条规则 74 秒,Agent 追问 18 秒)。**同一模型多次运行的结果并不稳定**(`step-router-v1` 另一次编出了 0 条规则),所以这些是单次测量,只能作为参考。
- **由此发现并修掉的问题**:① 工具调用循环里工具结果消息缺 `tool_call_id`,OpenAI 协议的服务端直接 400(Ollama 用的是 `tool_name`,现在两个字段都带,客户端对 OpenAI 端点会去掉 `tool_name`);② 云端会断连和限流,客户端加了有限次退避重试(断连、连接失败、429/5xx 重试,读超时不重试);③ 手册编出 0 条规则时原来仍显示 `ready`,对它验证会得到 `PASS`——现在会直接编译失败并说明原因。
- 如果本机开了系统代理,长时间无数据的非流式请求可能被代理掐断,可以用 `NO_PROXY=api.stepfun.com` 直连。
- API key 只通过环境变量传入,不写入任何文件或配置。

## 模型调优与消融实验(DGX Spark 上的真实测量)

视频理解这一步(视频 → 带时间戳的事件)是整条链路里最容易出错的环节,所以在 Spark 上做了微调和逐层消融。数据集是 NVIDIA `sop-server-fan-installation-data`(`praxiproof eval-sop` 评测):10 段训练录像,`Install_12`/`Install_13` 两段**留出**做测试——留出录像既没参与微调,也不允许作为参考图(`eval/nvidia_sop.py:build_references` 遇到测试录像直接抛错)。

**① DDM-Net 边界检测模型微调**:NVIDIA `pytorch:26.08` 容器里在 GB10 上训练,ResNet-50 骨干(`multiframes_resnet`),分辨率 224、每侧 5 帧,RandomResize/ColorJitter/GaussianBlur 数据增强,8 段训练 / 2 段验证。配置与脚本:`deploy/ddm/train/spark_clean.yaml`、`run_train_clean.sh`。

**② 后端消融**(事件检测,时间 IoU ≥ 0.3;原始结果在 `docs/eval/*.json`):

| 方案 | 精确率 | 召回率 | F1 | 序列相似度 | 秒/视频 |
|---|---|---|---|---|---|
| `local_vlm`:纯 VLM 滑窗(gemma4:31b)| 0.818 | 0.500 | 0.621 | 0.500 | 204 |
| `local_vlm`:加状态提示 | 0.714 | 0.278 | 0.400 | 0.389 | 165 |
| `local_vlm`:关闭窗口合并 | 0.588 | 0.556 | 0.571 | 0.667 | 398 |
| `ddm_vlm`:DDM 切分 + VLM 分类 | 0.654 | 0.944 | 0.773 | 0.731 | 234 |
| `ddm_vlm` + 参考图 + 多帧投票 + 手部检查(首版权重)| 0.548 | 0.944 | 0.694 | 0.612 | 1030 |
| **`ddm_vlm` + 参考图 + 多帧投票 + 手部检查(微调后权重)**| **1.000** | **0.944** | **0.971** | **0.945** | 385 |

读表:纯 VLM 滑窗召回只有 0.28–0.56;引入 DDM 边界切分把召回拉到 0.944;首版权重上叠加投票等提示工程反而拉低精确率并且慢了 4 倍;换成微调后的权重,精确率从 0.548 升到 1.000,同样的投票流程从 1030 秒降到 385 秒。注意这几行不是严格的单变量对照(方案之间同时改了多项),只能说明整体方向。

**③ VLM 选型**(18 个留出片段的单步分类准确率,`docs/eval/vlm_select*.json`):`gemma4:31b` 18/18(约 4.5 秒/片段);`qwen3.6:35b-a3b`(默认思考模式)17/18 但 29.7 秒/片段;`qwen3-vl:32b` 15/18;`qwen3.6` 关闭思考后掉到 5/18。所以视频侧用 gemma4,文本侧(手册编译、Agent)用 qwen3.6。

**局限**:评测集只有 2 段录像、18 个标注事件,F1 0.971 的置信区间很宽,不能外推为通用准确率;两个 demo 场景的 `BENCHMARK.md` 评的是确定性验证引擎,与这里的视频侧指标是两回事。

## 对照实验:直接问 VLM vs PraxiProof

为了说明"确定性验证引擎 + 证据链"比直接让 VLM 判断强在哪,在 Spark 上做了对照:6 段 NVIDIA 数据集里的编辑录像(`Install_12`/`Install_13` 各一段合规、缺机盖、电源先于风扇),真值已知。**基线**是 `gemma4:31b` 看到手册全文和 16 张带时间戳的关键帧后直接回答"是否合规",换 3 个采样相位各问一次;**PraxiProof** 是线上的一键流水线。原始数据 `docs/eval/baseline_vs_praxiproof.json`。

| 录像 | 真值 | 直接问 VLM(3 次采样)| PraxiProof |
|---|---|---|---|
| Install_12 合规 | Compliant | 3/3 正确 | Needs Evidence |
| Install_12 缺机盖 | Missing Step | 0/3(判成 Order Violation ×2、Compliant ×1)| **Missing Step** |
| Install_12 电源先于风扇 | Order Violation | 1/3(Compliant ×2)| **Order Violation** |
| Install_13 合规 | Compliant | 3/3 正确 | Needs Evidence |
| Install_13 缺机盖 | Missing Step | 0/3(全部判成 Compliant)| **Missing Step** |
| Install_13 电源先于风扇 | Order Violation | 3/3 正确 | **Order Violation** |

- **有违规的 4 段录像**:PraxiProof 4/4 判对类型,并给出手册引用和视频时间段;直接问 VLM 只有 4/12 次判对类型,其中 6/12 次直接说"合规"(漏报),同一段录像换个采样就会改口(6 段里只有 4 段前后一致)。
- **合规的 2 段录像**:直接问 VLM 6/6 判对,而 PraxiProof 都没有放行,给的是 "Needs Evidence"。原因是观测端漏检了一个风扇事件(5/6),电源和机盖只以 0.25 的低置信度检出,确定性引擎在证据不足时选择"证据不足"而不是猜——没有误报违规,但也**不能放行合规操作**,这是目前的短板,改进方向是提升观测端召回。
- 样本很小(6 段录像),只能说明方向。

## Agent Skills 设计

`compiler/agent_skill.py` 把每次验证结果编译成一份 Skill 包(`demo/sample-skill/` 下两个子目录分别对应上面两个 demo 场景的真实生成样例),设计上对齐 NVIDIA Verified Skills 规范的关键项:

- **窄触发、强路由**:`SKILL.md` 的 frontmatter `description` 明确写清楚"什么时候该用这个 skill",而不是把整本手册塞进去。
- **前置证据**:`## Rules that must hold` 每一条都带手册引用,`## Deviations seen in practice` 只列真实观测到的偏差,不臆测。
- **负向用例**:`evals/evals.json` 除了逐条规则生成的正向 case,还固定包含 3 条负向 case(离题问题、引用不存在的规则号、诱导 agent 跳过验证直接下结论),对应 Verified Skills 要求"评测集必须包含'正确答案是不触发'的场景"。
- **Skill Card**:`references/skill-card.md` 记录 Owner、依赖、风险与缓解措施,给人类审查者一个信任记录。
- **BENCHMARK.md**:`compiler/benchmark.py` 把 demo 三段录像(A/B/C)对着人工标注的期望 verdict 跑一遍,映射成 Correctness / Discoverability / Effectiveness / Security / Efficiency 五个维度。当前 Efficiency 和"带 skill / 不带 skill 的 agent 对比"这两项需要连上真实 Ollama 才能测,文档里如实标注为"未测量",不编造数字。

`ComplianceAgent`(`src/praxiproof/runtime/compliance_agent.py`)本身就是这份 Skill 在运行时的体现:它只能通过只读工具查证据,不能自己重新计算或推翻 verdict。

## 多智能体协同:Compliance Agent 委托 RCA Agent

回答"这条规则是不是过了"只需要读 verdict;但回答"为什么没过"需要看 verdict 背后没有被渲染出来的原始数据——观测到的每个事件的置信度、时间不确定度、以及它在对齐阶段有没有被正确映射到规则用到的词表。把这部分逻辑塞进 `ComplianceAgent` 会让它的工具集和系统提示词膨胀,而且这是两种不同的推理:一个是"查表复述",一个是"排查归因"。所以拆成了两个独立 prompt、独立工具集的 agent:

- **`ComplianceAgent`**(`runtime/compliance_agent.py`):面向用户,工具是高层只读查询(`get_verification_report`/`search_manual`/`inspect_video`),系统提示词禁止它自己猜测原因。
- **`RCAAgent`**(`runtime/rca_agent.py`):被 `ComplianceAgent` 通过新增的 `run_root_cause_analysis` 工具委托,拿到的是更底层的原始数据(`get_raw_observation` 返回所有事件,包含被置信度阈值过滤掉的弱置信度事件;`get_alignment` 返回每个原始标签有没有被正确映射到规则词表),把失败归因到 `VIDEO_GAP`/`LOW_CONFIDENCE`/`LABEL_MISMATCH`/`BOUNDARY_UNCERTAINTY`/`GENUINE_VIOLATION` 五类之一。返回契约是一行 `RCA_RESULT:` + 单行 JSON,调用方按字段消费,不解析自然语言——这个"严格结构化返回、由调用方委托而不是自己现场分析"的模式,是照着 NVIDIA `sop-rca-plugin` 的设计抄的(见前文对 `data/sopbp-src` 的分析)。

这套协作在界面里是可见的:运行详情页里每条未通过的规则都有"为什么没通过?"按钮,点击后直接调用 RCA agent,现场展示它调用了哪些原始数据工具、归到哪一类、依据和建议(`POST /api/runs/{id}/verdicts/{rule}/analyze`);在"询问合规智能体"里提问时,回答下方会展开完整的协作轨迹——Compliance Agent 的每次工具调用,以及它委托 RCA agent 之后 RCA agent 自己的工具调用和结构化结论(`/api/agent/ask` 的 `tool_calls` 里带 `sub_trace`)。侧边栏的"评测"页(`/api/evaluation`)把本文的微调消融、VLM 选型、与直接问 VLM 的对照、StepFun 对比集中呈现,数据直接读 `docs/eval/*.json`,不是手写进页面的。

真实模型的输出格式并不总是听话:本地 qwen3.6 会省略 `RCA_RESULT:` 前缀、把 JSON 排成多行,最初严格的解析器在真机上 3 次全部失败(mock 测试全过)。现在改成取回复里第一个合法的 JSON 对象并校验 `category` 是否属于五类之一。

两个 agent 用的是同一个 `LLM` 客户端(`OllamaClient`/`OpenAICompatibleClient` 皆可),但系统提示词、工具集、返回契约完全独立,是真正的委托关系而不是同一个 prompt 里塞更多工具。测试见 `tests/test_rca_agent.py`(用 `FakeLLM` 模拟两个 agent 交替的工具调用序列,不需要真实 LLM)。

## 技术栈

- **LLM/VLM 推理**:本地 Ollama,或任意 OpenAI 兼容端点(`PRAXIPROOF_LLM_PROVIDER=openai`,见上文),手册编译用 LLM、视频理解用 VLM,模型名可在运行时热切换。
- **NVIDIA 技术栈**:DDM-Net 时序边界检测(来自 `NVIDIA/sop-monitoring-blueprints` 的 training blueprint),GPU 推理容器化部署;`nvidia_sop` 后端预留了对接官方 `sop-inference-bp` 推理服务的接口。
- **Web**:FastAPI + 内置静态双语前端。
- **StepFun 阶跃星辰模型**:通过上面的 OpenAI 兼容 provider 接入,已用真实 API 验证 `step-3.5-flash`/`step-3.7-flash`/`step-router-v1`(手册编译、工具调用、Agent 追问),详见上文。

## 已知限制 / Roadmap

- [ ] 把 Spark 上的线上服务切到 StepFun(需要在 systemd 里配置环境变量,目前线上仍用本地 Ollama),并评估 StepFun 的 VLM 能力用于视频理解。
- [ ] 评测集目前只有 2 段留出录像(共 18 个标注事件),样本量小;补充更多留出录像后重跑 `praxiproof eval-sop`,并把微调扩展到 VLM(`sop-cr-finetuning-plugin`)。
- [ ] `BENCHMARK.md` 补上真实 Ollama 环境下的 Efficiency 与"带/不带 skill"对比。
- [ ] 录制 Demo 演示视频、撰写黑客松十日谈征文、补团队合影。
