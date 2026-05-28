const path = require("path");
const fs = require("fs");
const PptxGenJS = require("pptxgenjs");
const {
  imageSizingCrop,
  imageSizingContain,
} = require("./pptxgenjs_helpers/image");
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers/layout");

function firstExisting(paths) {
  for (const p of paths) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error(`Path not found in candidates: ${paths.join(" | ")}`);
}

const scriptDir = __dirname;
const assetsDir = firstExisting([
  path.join(scriptDir, "assets"),
  path.join(scriptDir, "..", "..", "output", "ppt", "assets"),
]);
const distDir = path.join(scriptDir, "dist");
fs.mkdirSync(distDir, { recursive: true });

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "OpenAI Codex";
pptx.company = "安徽工业大学";
pptx.subject = "智能语音聊天机器人设计与实现毕业答辩";
pptx.title = "智能语音聊天机器人设计与实现";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineSlideMaster({
  title: "AHUT_MASTER",
  background: { color: "F7FAFC" },
  objects: [
    { rect: { x: 0, y: 0, w: 13.333, h: 0.18, fill: { color: "0E3A66" }, line: { color: "0E3A66" } } },
    { rect: { x: 0, y: 7.18, w: 13.333, h: 0.32, fill: { color: "0E3A66" }, line: { color: "0E3A66" } } },
  ],
  slideNumber: {
    x: 12.35,
    y: 7.18,
    w: 0.6,
    h: 0.22,
    fontFace: "Microsoft YaHei",
    fontSize: 9,
    color: "FFFFFF",
    align: "right",
  },
});

const C = {
  navy: "0E3A66",
  blue: "1F6FB2",
  cyan: "31B6D6",
  teal: "0EA5A6",
  bg: "F7FAFC",
  text: "1F2937",
  sub: "5B6675",
  light: "EAF2FA",
  border: "D7E3F0",
  white: "FFFFFF",
  accent: "F59E0B",
};

const A = {
  cover: path.join(assetsDir, "cover-hero-ai.png"),
  runtimeAi: path.join(assetsDir, "runtime-concept-ai.png"),
  thanksBg: path.join(assetsDir, "thanks-bg-ai.png"),
  architecture: path.join(assetsDir, "system_architecture.png"),
  modules: path.join(assetsDir, "system_function_modules.png"),
  databaseEr: path.join(assetsDir, "database_er.png"),
  realtimeSeq: path.join(assetsDir, "realtime_sequence.png"),
  voiceFlow: path.join(assetsDir, "voice_interaction_flow.png"),
  rag: path.join(assetsDir, "fig4-4-rag-workflow.png"),
  chat: path.join(assetsDir, "fig5-2-chat.png"),
  provider: path.join(assetsDir, "fig5-5-provider.png"),
  knowledge: path.join(assetsDir, "fig5-6-knowledge.png"),
  voice: path.join(assetsDir, "fig5-8-voice.png"),
  interrupt: path.join(assetsDir, "fig5-10-realtime-interrupt-scene.png"),
};

function addFooter(slide, shortTitle) {
  slide.addText(`安徽工业大学 | ${shortTitle}`, {
    x: 0.35,
    y: 7.18,
    w: 5.8,
    h: 0.2,
    fontFace: "Microsoft YaHei",
    fontSize: 9,
    color: "FFFFFF",
    margin: 0,
  });
}

function addTitle(slide, title, subtitle) {
  slide.addText(title, {
    x: 0.6,
    y: 0.42,
    w: 7.6,
    h: 0.5,
    fontFace: "SimHei",
    fontSize: 24,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.62,
      y: 0.94,
      w: 7.9,
      h: 0.24,
      fontFace: "Microsoft YaHei",
      fontSize: 10.5,
      color: C.sub,
      margin: 0,
    });
  }
  slide.addShape(pptx.ShapeType.line, {
    x: 0.6,
    y: 1.26,
    w: 1.5,
    h: 0,
    line: { color: C.cyan, pt: 2.5 },
  });
}

function addBulletList(slide, items, opts = {}) {
  const x = opts.x ?? 0.8;
  const y = opts.y ?? 1.55;
  const w = opts.w ?? 5.2;
  const h = opts.h ?? 4.4;
  const fontSize = opts.fontSize ?? 18;
  const gap = opts.gap ?? 0.15;
  const runs = [];
  items.forEach((item, idx) => {
    runs.push({
      text: item,
      options: {
        bullet: { indent: fontSize * 0.9 },
        hanging: 2,
        breakLine: idx !== items.length - 1,
      },
    });
  });
  slide.addText(runs, {
    x,
    y,
    w,
    h,
    fontFace: "Microsoft YaHei",
    fontSize,
    color: C.text,
    margin: 0.02,
    breakLine: true,
    paraSpaceAfterPt: gap * 24,
    valign: "top",
  });
}

function addCard(slide, x, y, w, h, title, body, color = C.white) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.08,
    fill: { color },
    line: { color: C.border, pt: 1 },
    shadow: { type: "outer", color: "9AA7B6", blur: 1, angle: 45, distance: 1, opacity: 0.1 },
  });
  slide.addText(title, {
    x: x + 0.18,
    y: y + 0.12,
    w: w - 0.36,
    h: 0.24,
    fontFace: "SimHei",
    fontSize: 13,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  slide.addText(body, {
    x: x + 0.18,
    y: y + 0.42,
    w: w - 0.36,
    h: h - 0.52,
    fontFace: "Microsoft YaHei",
    fontSize: 10.5,
    color: C.text,
    margin: 0,
    valign: "top",
  });
}

function addSectionChip(slide, text, x, y, fill = C.light) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w: 1.48,
    h: 0.34,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: fill, pt: 1 },
  });
  slide.addText(text, {
    x,
    y: y + 0.03,
    w: 1.48,
    h: 0.22,
    align: "center",
    fontFace: "Microsoft YaHei",
    fontSize: 9.5,
    bold: true,
    color: C.blue,
    margin: 0,
  });
}

function addCaption(slide, text, x, y, w) {
  slide.addText(text, {
    x,
    y,
    w,
    h: 0.22,
    fontFace: "Microsoft YaHei",
    fontSize: 8.5,
    color: C.sub,
    italic: true,
    align: "center",
    margin: 0,
  });
}

function finalizeSlide(slide, shortTitle) {
  addFooter(slide, shortTitle);
  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

// 1 封面
{
  const slide = pptx.addSlide();
  slide.background = { color: "071B33" };
  slide.addImage({ path: A.cover, ...imageSizingCrop(A.cover, 0, 0, 13.333, 7.5) });
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 6.1,
    h: 7.5,
    fill: { color: "071B33", transparency: 22 },
    line: { color: "071B33", transparency: 100 },
  });
  slide.addText("智能语音聊天机器人设计与实现", {
    x: 0.7,
    y: 1.15,
    w: 5.2,
    h: 1.0,
    fontFace: "SimHei",
    fontSize: 24,
    bold: true,
    color: C.white,
    margin: 0,
    valign: "mid",
  });
  slide.addText("基于 React、FastAPI 与检索增强生成的多模态语音对话系统", {
    x: 0.72,
    y: 2.18,
    w: 5.0,
    h: 0.5,
    fontFace: "Microsoft YaHei",
    fontSize: 11,
    color: "D8E7F6",
    margin: 0,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.72,
    y: 2.8,
    w: 1.7,
    h: 0,
    line: { color: "4CC9F0", pt: 2.3 },
  });
  slide.addText("专业：计算机科学与技术\n班级：计225\n姓名：廖园\n学号：229074182\n指导教师：王朋飞\n答辩日期：2026年5月", {
    x: 0.78,
    y: 3.15,
    w: 3.7,
    h: 2.4,
    fontFace: "Microsoft YaHei",
    fontSize: 13,
    color: C.white,
    breakLine: true,
    paraSpaceAfterPt: 10,
    margin: 0,
  });
  slide.addText("安徽工业大学毕业设计答辩", {
    x: 0.78,
    y: 6.75,
    w: 3.2,
    h: 0.28,
    fontFace: "Microsoft YaHei",
    fontSize: 10,
    color: "C7D9ED",
    margin: 0,
  });
}

// 2 研究背景与课题意义
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "研究背景与课题意义", "为什么要做这套智能语音聊天机器人系统");
  addSectionChip(slide, "问题导向", 0.8, 1.45);
  addBulletList(slide, [
    "传统聊天机器人以文本输入为主，语音交互过程不够自然，难以满足连续对话需求。",
    "通用大模型缺少私有资料支撑，面对课程文档或项目配置问题时回答容易泛化。",
    "文本、语音输入和实时通话常被割裂实现，系统状态分散，调试与扩展成本较高。",
    "因此，需要一套围绕统一运行时组织的多模态语音对话系统，兼顾实时体验与工程可控性。",
  ], { x: 0.85, y: 1.95, w: 6.15, h: 4.9, fontSize: 17 });
  addCard(slide, 7.35, 1.75, 5.05, 1.2, "交互层问题", "语音体验不连续、打断响应弱、交互节奏偏慢", "F9FCFF");
  addCard(slide, 7.35, 3.05, 5.05, 1.2, "知识层问题", "通用模型缺少项目资料支撑，回答难以贴近真实业务材料", "F9FCFF");
  addCard(slide, 7.35, 4.35, 5.05, 1.2, "工程层问题", "链路与配置缺少统一组织，维护、替换与扩展难度较高", "F9FCFF");
  finalizeSlide(slide, "研究背景与课题意义");
}

// 3 研究目标与论文工作
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "研究目标与论文工作", "系统目标不是单一功能验证，而是形成完整工程闭环");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.55, w: 11.7, h: 0.78, rectRadius: 0.08,
    fill: { color: "EAF4FF" }, line: { color: "B9D6F2", pt: 1.2 },
  });
  slide.addText("设计并实现一个支持文本、语音输入、实时语音通话和知识增强的智能语音聊天机器人系统。", {
    x: 1.0, y: 1.78, w: 11.2, h: 0.28,
    fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: C.navy, align: "center", margin: 0,
  });
  const cards = [
    ["需求分析与数据库设计", "梳理功能需求、非功能需求和核心数据结构。"] ,
    ["统一会话运行时", "统一组织文本对话、语音输入和实时通话。"] ,
    ["双语音链路实现", "实现分阶段链路和一体化实时链路两种策略。"] ,
    ["知识与个性化能力", "接入RAG、记忆管理、人格配置与音色管理。"] ,
    ["系统测试与验证", "通过真实页面、测试用例与链路结果验证可用性。"] ,
  ];
  cards.forEach((item, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const x = 0.9 + col * 5.9 + (row === 2 ? 2.95 : 0);
    const y = row < 2 ? 2.8 + row * 1.5 : 5.8;
    const w = row === 2 ? 5.6 : 5.2;
    addCard(slide, x, y, w, 1.15, item[0], item[1], "FFFFFF");
  });
  finalizeSlide(slide, "研究目标与论文工作");
}

// 4 系统总体架构
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统总体架构", "整场答辩的总览：前端、后端、数据与外部服务协同工作");
  slide.addImage({ path: A.architecture, ...imageSizingContain(A.architecture, 0.6, 1.55, 8.25, 5.0) });
  addCaption(slide, "系统总体架构图", 0.9, 6.48, 7.6);
  addCard(slide, 9.15, 1.7, 3.7, 0.95, "前端交互层", "聊天中心、语音输入、实时通话、运行状态与指标展示");
  addCard(slide, 9.15, 2.8, 3.7, 1.0, "后端服务编排层", "FastAPI 统一暴露 REST API 与 WebSocket 接口，组织对话链路");
  addCard(slide, 9.15, 3.95, 3.7, 0.95, "数据存储层", "PostgreSQL 保存会话、配置、知识库与审计数据，pgvector 存向量");
  addCard(slide, 9.15, 5.05, 3.7, 1.0, "外部模型与语音服务", "文本模型、语音识别、语音合成与实时模型按 Provider 统一接入");
  finalizeSlide(slide, "系统总体架构");
}

// 5 核心功能模块
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "核心功能模块", "系统不是单一聊天页，而是一套完整的多模态语音交互平台");
  slide.addImage({ path: A.modules, ...imageSizingContain(A.modules, 0.65, 1.65, 6.75, 4.9) });
  addCaption(slide, "系统功能模块图", 1.1, 6.5, 5.9);
  addCard(slide, 7.75, 1.8, 4.6, 2.1, "用户侧能力", "文本对话、语音输入、实时语音通话、知识增强问答。通过统一会话运行时向用户提供连续、可感知的交互体验。 ", "F9FCFF");
  addCard(slide, 7.75, 4.15, 4.6, 2.1, "管理侧能力", "Provider 配置、链路配置、人格配置、音色管理、知识库管理与系统设置。系统既能聊天，也能被维护、被替换、被扩展。", "F9FCFF");
  finalizeSlide(slide, "核心功能模块");
}

// 6 关键设计一：统一会话运行时
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计一：统一会话运行时", "将文本对话、语音输入和实时通话纳入同一运行时模型");
  slide.addImage({ path: A.runtimeAi, ...imageSizingContain(A.runtimeAi, 6.95, 1.5, 5.7, 4.8) });
  addSectionChip(slide, "核心思想", 0.85, 1.45);
  addBulletList(slide, [
    "统一管理会话标识、运行状态、转写文本、消息列表和轮次性能指标。",
    "通过一致的事件模型驱动页面更新，减少多条链路并行时的状态分散问题。",
    "把文本对话、语音输入和实时通话抽象成统一接口，便于扩展与替换。",
    "为后续的链路切换、指标采集和异常回退提供稳定基础。",
  ], { x: 0.9, y: 1.95, w: 5.55, h: 3.8, fontSize: 17 });
  addCard(slide, 0.92, 5.75, 1.45, 0.78, "状态", "待机、监听、思考、播报");
  addCard(slide, 2.48, 5.75, 1.45, 0.78, "消息", "会话流与转写文本");
  addCard(slide, 4.04, 5.75, 1.45, 0.78, "指标", "首字延迟、总耗时等");
  addCard(slide, 5.60, 5.75, 1.45, 0.78, "事件", "统一分发与订阅");
  finalizeSlide(slide, "统一会话运行时");
}

// 7 关键设计二：双语音链路
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计二：双语音链路", "保留双链路不是重复实现，而是为了兼顾实时体验和工程可控性");
  addCard(slide, 0.75, 1.65, 3.95, 2.0, "分阶段语音链路", "先完成语音识别，再组织知识检索、文本生成和语音播报。优点是模块边界清晰、便于调试、便于替换。", "F9FCFF");
  addCard(slide, 4.95, 1.65, 3.95, 2.0, "一体化实时语音链路", "通过 WebSocket 持续传输音频块，边接收边处理。优点是交互节奏更紧凑、插话体验更自然。", "F9FCFF");
  addCard(slide, 9.15, 1.65, 3.45, 2.0, "设计结论", "面向不同场景保留两种策略：一条强调可控性，一条强调实时性，统一由运行时组织。", "FFF8E8");
  slide.addImage({ path: A.voiceFlow, ...imageSizingContain(A.voiceFlow, 0.8, 4.0, 5.7, 2.0) });
  slide.addImage({ path: A.realtimeSeq, ...imageSizingContain(A.realtimeSeq, 6.85, 4.0, 5.7, 2.0) });
  addCaption(slide, "分阶段语音交互流程", 1.1, 6.2, 5.0);
  addCaption(slide, "实时语音通话时序图", 7.2, 6.2, 5.0);
  finalizeSlide(slide, "双语音链路");
}

// 8 关键设计三：RAG 知识增强
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计三：RAG知识增强", "RAG：检索增强生成，让系统从能聊天变成能结合项目资料回答");
  slide.addImage({ path: A.rag, ...imageSizingContain(A.rag, 6.6, 1.6, 6.0, 4.8) });
  addSectionChip(slide, "流程说明", 0.85, 1.48);
  addCard(slide, 0.9, 1.95, 5.1, 0.9, "步骤1 用户问题输入", "系统接收文本问题或由语音识别转写后的问题。", "FFFFFF");
  addCard(slide, 0.9, 2.95, 5.1, 0.9, "步骤2 检索门控判断", "先判断是否需要知识增强，避免每轮都无差别触发检索。", "FFFFFF");
  addCard(slide, 0.9, 3.95, 5.1, 0.9, "步骤3 向量召回与重排序", "从知识库切片中筛选相关内容，构造高质量知识上下文。", "FFFFFF");
  addCard(slide, 0.9, 4.95, 5.1, 0.9, "步骤4 上下文注入与回答生成", "把知识片段与会话历史共同注入模型，提升资料型问答效果。", "FFFFFF");
  finalizeSlide(slide, "RAG知识增强");
}

// 9 数据库与数据设计
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "数据库与数据设计", "数据库设计围绕会话、配置、知识和审计四类数据展开");
  slide.addImage({ path: A.databaseEr, ...imageSizingContain(A.databaseEr, 0.55, 1.6, 7.4, 4.9) });
  addCaption(slide, "数据库 E-R 图", 1.5, 6.45, 5.4);
  addCard(slide, 8.25, 1.8, 4.0, 0.95, "会话与消息", "保存会话标题、消息内容、内容类型和交互历史。");
  addCard(slide, 8.25, 2.95, 4.0, 0.95, "上下文记忆", "维护短期记忆、中期摘要和长期向量记忆。");
  addCard(slide, 8.25, 4.10, 4.0, 0.95, "Provider 与模型目录", "统一保存模型服务地址、模型清单和状态信息。");
  addCard(slide, 8.25, 5.25, 4.0, 0.95, "知识与审计", "保存知识库、文档切片、向量内容与链路审计记录。");
  finalizeSlide(slide, "数据库与数据设计");
}

// 10 系统实现与界面展示
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统实现与界面展示", "用真实页面说明系统已经形成完整实现，而不是概念设计");
  const items = [
    [A.chat, 0.75, 1.55, "聊天中心页面", "主交互入口，负责会话与实时语音状态展示。"] ,
    [A.provider, 6.95, 1.55, "厂商与模型管理", "统一维护 Provider 配置、连通性和模型目录。"] ,
    [A.knowledge, 0.75, 4.25, "知识库管理页面", "负责文档上传、检索测试与参数维护。"] ,
    [A.voice, 6.95, 4.25, "音色管理页面", "支持音色创建、样本上传、试听与克隆。"] ,
  ];
  items.forEach(([img, x, y, title, desc]) => {
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y, w: 5.6, h: 2.05, rectRadius: 0.06,
      fill: { color: "FFFFFF" }, line: { color: C.border, pt: 1 },
    });
    slide.addImage({ path: img, ...imageSizingContain(img, x + 0.12, y + 0.12, 2.65, 1.42) });
    slide.addText(title, {
      x: x + 2.95, y: y + 0.18, w: 2.35, h: 0.22,
      fontFace: "SimHei", fontSize: 12.5, bold: true, color: C.navy, margin: 0,
    });
    slide.addText(desc, {
      x: x + 2.95, y: y + 0.52, w: 2.35, h: 0.86,
      fontFace: "Microsoft YaHei", fontSize: 9.5, color: C.text, margin: 0,
    });
  });
  finalizeSlide(slide, "系统实现与界面展示");
}

// 11 系统测试与结果分析
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统测试与结果分析", "测试重点是功能闭环、链路差异和资料型问答效果");
  const rows = [
    ["测试项", "观察结果", "结论"],
    ["文本对话功能测试", "会话创建、消息保存和回复生成可以稳定完成。", "通过"],
    ["实时通话链路测试", "支持持续传输、局部转写、播报和插话打断。", "通过"],
    ["知识库开启/关闭对比", "资料型问答在开启知识库后更具体、更贴近文档。", "有效"],
    ["音色样本上传与异常处理", "克隆成功路径与错误路径均有明确反馈。", "通过"],
  ];
  const colXs = [0.72, 3.25, 10.35];
  const colWs = [2.45, 7.0, 1.55];
  const rowY = 1.55;
  const rowH = 0.53;
  rows.forEach((row, rIdx) => {
    row.forEach((cell, cIdx) => {
      slide.addShape(pptx.ShapeType.rect, {
        x: colXs[cIdx],
        y: rowY + rIdx * rowH,
        w: colWs[cIdx],
        h: rowH,
        fill: { color: rIdx === 0 ? C.navy : C.white },
        line: { color: "C8D7E6", pt: 1 },
      });
      slide.addText(cell, {
        x: colXs[cIdx] + 0.08,
        y: rowY + rIdx * rowH + 0.08,
        w: colWs[cIdx] - 0.16,
        h: rowH - 0.16,
        fontFace: "Microsoft YaHei",
        fontSize: rIdx === 0 ? 10 : 9.5,
        bold: rIdx === 0,
        color: rIdx === 0 ? C.white : C.text,
        align: cIdx === 1 ? "left" : "center",
        valign: "mid",
        margin: 0,
      });
    });
  });
  addCard(slide, 0.8, 4.55, 3.9, 1.3, "结论1 核心闭环已完成", "文本问答、知识检索、实时通话和音色管理已经形成可运行、可展示、可分析的整体。", "F9FCFF");
  addCard(slide, 4.95, 4.55, 3.9, 1.3, "结论2 双链路各有适用场景", "分阶段链路更利于调试与替换，一体化实时链路更强调连续交互体验。", "F9FCFF");
  addCard(slide, 9.10, 4.55, 3.55, 1.3, "结论3 仍受外部条件影响", "网络、浏览器兼容性和模型服务稳定性仍会影响实时体验。", "FFF8E8");
  slide.addImage({ path: A.interrupt, ...imageSizingContain(A.interrupt, 4.0, 6.0, 5.35, 1.0) });
  finalizeSlide(slide, "系统测试与结果分析");
}

// 12 项目特点与创新点
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "项目特点与创新点", "答辩老师最应该记住的三点");
  addCard(slide, 0.8, 1.95, 3.85, 3.5, "统一会话运行时", "把文本对话、语音输入和实时语音通话纳入同一运行时，统一管理状态、消息流、转写文本和性能指标，从根源上减少多链路状态割裂问题。", "F7FBFF");
  addCard(slide, 4.75, 1.95, 3.85, 3.5, "双语音链路设计", "同时保留分阶段链路与一体化实时链路，在可控性和实时性之间提供可切换的实现策略，适应不同测试和应用场景。", "F7FBFF");
  addCard(slide, 8.70, 1.95, 3.85, 3.5, "知识与个性化闭环", "通过 RAG、记忆管理、人格配置和音色管理，把问答、知识、角色和语音风格组织成可扩展的完整系统能力。", "F7FBFF");
  slide.addText("一句话概括：本课题不是接入若干模型接口，而是构建了一套可运行、可维护、可扩展的多模态语音交互平台。", {
    x: 1.0, y: 6.0, w: 11.3, h: 0.45,
    fontFace: "Microsoft YaHei", fontSize: 15, bold: true, color: C.navy, align: "center", margin: 0,
  });
  finalizeSlide(slide, "项目特点与创新点");
}

// 13 结论与展望
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "结论与展望", "完成了从架构、实现到测试的完整闭环");
  addSectionChip(slide, "结论", 0.85, 1.45);
  addBulletList(slide, [
    "已实现一个支持文本、语音输入、实时语音通话和知识增强的多模态智能语音聊天机器人系统。",
    "系统围绕统一会话运行时组织交互、知识、配置与语音能力，整体具备较好的扩展性与工程可控性。",
    "通过真实页面、测试用例和链路验证，说明系统已经具备可运行、可展示和可分析的答辩基础。",
  ], { x: 0.9, y: 1.95, w: 5.65, h: 3.2, fontSize: 17 });
  addSectionChip(slide, "展望", 7.0, 1.45, "EEF8F8");
  addCard(slide, 7.0, 1.95, 5.2, 0.9, "方向1 识别稳定性", "进一步优化复杂噪声环境下的语音识别鲁棒性。", "FFFFFF");
  addCard(slide, 7.0, 3.0, 5.2, 0.9, "方向2 长时对话能力", "增强长期记忆召回与多轮调度策略，提高连续对话一致性。", "FFFFFF");
  addCard(slide, 7.0, 4.05, 5.2, 0.9, "方向3 多模态扩展", "拓展图像理解或更丰富的多模态输入输出能力。", "FFFFFF");
  slide.addImage({ path: A.interrupt, ...imageSizingContain(A.interrupt, 7.75, 5.25, 3.85, 1.25) });
  finalizeSlide(slide, "结论与展望");
}

// 14 致谢
{
  const slide = pptx.addSlide();
  slide.background = { color: "081B34" };
  slide.addImage({ path: A.thanksBg, ...imageSizingCrop(A.thanksBg, 0, 0, 13.333, 7.5) });
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: 13.333, h: 7.5,
    fill: { color: "081B34", transparency: 22 },
    line: { color: "081B34", transparency: 100 },
  });
  slide.addText("感谢各位老师聆听", {
    x: 2.0, y: 2.25, w: 9.3, h: 0.8,
    fontFace: "SimHei", fontSize: 28, bold: true, color: C.white, align: "center", margin: 0,
  });
  slide.addText("恳请各位老师批评指正", {
    x: 2.1, y: 3.2, w: 9.1, h: 0.42,
    fontFace: "Microsoft YaHei", fontSize: 16, color: "DCEAF8", align: "center", margin: 0,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 4.7, y: 4.05, w: 3.9, h: 0,
    line: { color: "59C0E8", pt: 1.8 },
  });
  slide.addText("智能语音聊天机器人设计与实现", {
    x: 3.1, y: 4.35, w: 7.1, h: 0.32,
    fontFace: "Microsoft YaHei", fontSize: 11.5, color: "DCEAF8", align: "center", margin: 0,
  });
}

(async () => {
  const outPath = path.join(distDir, "智能语音聊天机器人设计与实现-毕业答辩PPT.pptx");
  await pptx.writeFile({ fileName: outPath });
  console.log(outPath);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
