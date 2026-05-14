# Apple Watch ECG Analyzer

> **Claude Code Skill** — 同时可作为独立 Python CLI 工具使用。/
> **Claude Code Skill** — also usable as a standalone Python CLI tool.

从 Apple Watch 心电图 PDF 中提取波形数据，检测 QRS 波群，计算心率与 RR 间期，筛查早搏（APC/PVC）。/
Extract and analyze Apple Watch ECG PDF exports: waveform extraction, QRS detection, heart rate / RR interval analysis, and premature beat (APC/PVC) screening.

> ⚠️ **非医疗设备。** 本工具仅供信息参考与研究用途，不能替代执业医师的诊断与治疗方案。/
> **Not a medical device.** For informational and research purposes only. Always consult a licensed physician for diagnosis and treatment decisions.

---

## 功能 / Features

- **PDF 波形提取** — 解析 Apple Watch ECG PDF，提取原始时间/电压数据（512 Hz，Lead I）
- **QRS 检测** — 纯 Python 实现 Pan-Tompkins 风格算法（无 numpy/scipy 依赖）
- **心率与 RR 间期** — 计算平均心率、RR 统计、基础 HRV（SDNN 等效）
- **早搏筛查** — 检测并分类 APC/PVC 候选，带置信度分级
- **质量评估** — 数据完整性检查、Row 0 偏移检测、伪迹标记指引
- **多格式输出** — JSON（结构化）或 CSV（原始波形）

---

## 安装 / Installation

```bash
pip install pdfplumber
```

或：

```bash
pip install -r requirements.txt
```

需要 Python 3.8+。

---

## 使用 / Usage

### 步骤 1：从 PDF 提取波形

```bash
python3 scripts/ecg_extract.py <input.pdf> -o output.json --pretty
python3 scripts/ecg_extract.py <input.pdf> --csv -o waveform.csv
```

**输出 JSON 结构：**
- `metadata` — 患者姓名、出生日期、记录时间、心率、心律、设备信息
- `waveform.time_voltage` — `{t, v, row}` 数组（时间秒、电压 mV、行号 0/1/2）
- `quality` — 数据完整性、Row 0 偏移信息

**关键说明：**
- Apple Watch PDF 采用 3 行布局（每行 10 秒）
- Row 0 因 ECG 图标占用有约 0.36 秒偏移
- 每行基线独立计算（中位数），避免跨行跳变

### 步骤 2：QRS 检测与分析

```bash
python3 scripts/ecg_qrs_detect.py output.json --pretty -o analysis.json
```

**输出 JSON 结构：**
- `peaks` — 检测到的 R 波峰（时间、电压、索引）
- `rr_intervals` — 连续 RR 间期（毫秒）
- `summary` — 总心搏数、平均心率、RR 统计
- `summary.potential_ectopic` — 早搏候选（含置信度与分类）

**示例输出：**
```
Beats: 42, HR: 84.0 bpm
RR: 714.3ms (std: 45.2ms)
Potential ectopic: 2
  t=12.34s, RR=280ms (39%) [PVC, high]
  t=18.56s, RR=420ms (59%) [APC, medium]
```

---

## 算法概览 / Algorithm Overview

详见 [`references/analysis_guide.md`](references/analysis_guide.md)。

**流水线：**

1. **带通滤波** — 0.5 Hz 高通（去除基线漂移）+ 40 Hz 低通（去除噪声）
2. **差分 + 平方 + 积分** — 150 ms 移动窗口生成能量包络
3. **自适应阈值峰值检测** — 基于信号/噪声水平的动态阈值，200 ms 不应期
4. **回搜 R 波峰** — 将能量峰值映射到滤波信号的真实最大电压点
5. **RR 分析与早搏筛查** — 联律间期 < 中位 RR 的 80% 即标记为早搏

**灵敏度调节：** 编辑 `scripts/ecg_qrs_detect.py` 中：
```python
threshold1 = noise_level + 0.25 * (signal_level - noise_level)
```
增大系数（如 0.35）更严格，减小（如 0.15）更灵敏。

---

## 伪迹验证 / Artifact Verification

当算法标记 PVC 或极短 RR（< 300 ms）时，对照原始 PDF 验证：

- 正常 R 波峰：0.3–0.8 mV。> 1.5 mV 提示伪迹
- 正常 QRS：尖锐、窄（< 120 ms）。宽弧或平台 → 伪迹
- 单个怪异心搏夹在正常心搏间 → 更可能是伪迹而非病理
- 详见 `references/analysis_guide.md` 完整验证协议

---

## 限制 / Limitations

- **单导联** — Apple Watch Lead I，无法区分所有形态
- **无 P 波检测** — APC vs PVC 分类仅基于时序，是概率性的
- **30 秒快照** — 捕捉偶发事件但可能漏掉间歇性模式
- **仅中文 PDF** — 元数据解析针对中文区域 Apple Watch ECG PDF
- **阈值依赖** — 极低振幅 QRS 或显著运动伪迹时效果下降

---

## AI Agent 兼容 / AI Agent Compatibility

本工具同时是 **Claude Code Skill** 和通用 Python CLI 脚本：

| Agent | 使用方式 |
|---|---|
| **Claude Code** | 作为 Skill 安装到 `~/.claude/skills/`，Claude 自动识别并调用；或直接执行脚本 |
| **Codex** | 直接通过 Bash 工具执行脚本 |
| **OpenClaw** | 原生 Skill 支持（通过 `SKILL.md` 包装脚本） |

脚本仅读写本地文件，无网络调用、无 API Key、除 `pdfplumber` 外无外部依赖。

### 作为 Claude Code Skill 安装

```bash
git clone https://github.com/TZPlus/apple-watch-ecg-analyzer.git \
  ~/.claude/skills/apple-watch-ecg-analyzer
```

Claude Code 会在对话中自动识别 Apple Watch ECG PDF 相关请求并调用本 Skill。

---

## 协议 / License

MIT License — 详见 [LICENSE](LICENSE).

## 致谢 / Acknowledgments

- Pan & Tompkins, 1985 — 原始实时 QRS 检测算法
- Apple Watch ECG: 512 Hz, Lead I, 10 mm/mV, 25 mm/s
