## 项目定位

Apple Watch ECG PDF 分析工具。提取波形数据，检测 QRS 波群，计算心率与 RR 间期，筛查早搏（APC/PVC）。

## 技术栈

Pure Python，无 numpy/scipy 依赖。仅需 pdfplumber 解析 PDF。

## 验证命令

```bash
python3 ecg_extract.py example.pdf --pretty
python3 ecg_qrs_detect.py example.json --pretty
```

## 目录结构

```
├── ecg_extract.py      # PDF 波形提取
├── ecg_qrs_detect.py   # QRS 检测与早搏筛查
├── docs/               # 算法文档
└── requirements.txt
```

## 约束

- 仅支持 Apple Watch 导出的单页 ECG PDF（512Hz，Lead I）
- 不替代医疗诊断，输出需经专业医师确认
- 不处理 12 导联 ECG 或其他设备格式
