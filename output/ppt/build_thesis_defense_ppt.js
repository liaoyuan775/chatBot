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

function addMiniLabel(slide, text, x, y, w = 0.95, fill = "EAF2FA") {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.28, rectRadius: 0.06,
    fill: { color: fill }, line: { color: fill, pt: 1 },
  });
  slide.addText(text, {
    x, y: y + 0.03, w, h: 0.16,
    fontFace: "Microsoft YaHei", fontSize: 8.5, bold: true, color: C.blue, align: "center", margin: 0,
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

function addScreenshotPanel(slide, img, x, y, w, h, title, desc) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.06,
    fill: { color: "FFFFFF" },
    line: { color: C.border, pt: 1 },
    shadow: { type: "outer", color: "9AA7B6", blur: 1, angle: 45, distance: 1, opacity: 0.08 },
  });
  slide.addText(title, {
    x: x + 0.18,
    y: y + 0.14,
    w: w - 0.36,
    h: 0.24,
    fontFace: "SimHei",
    fontSize: 14,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  slide.addText(desc, {
    x: x + 0.18,
    y: y + 0.42,
    w: w - 0.36,
    h: 0.3,
    fontFace: "Microsoft YaHei",
    fontSize: 10.5,
    color: C.sub,
    margin: 0,
  });
  slide.addImage({ path: img, ...imageSizingContain(img, x + 0.18, y + 0.8, w - 0.36, h - 0.98) });
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
  addTitle(slide, "研究背景与课题意义", "从研究现状、现有不足和课题价值三方面说明选题依据");
  addSectionChip(slide, "背景现状", 0.8, 1.45);
  addBulletList(slide, [
    "大语言模型、语音识别与语音合成快速发展，语音交互系统正从单轮问答走向连续对话。",
    "面向教育陪练、智能助手等场景，系统不仅要会回答，还要具备低时延、可打断和上下文连续能力。",
  ], { x: 0.85, y: 1.95, w: 6.05, h: 2.2, fontSize: 17 });
  addSectionChip(slide, "现有不足", 0.8, 4.18);
  addBulletList(slide, [
    "现有系统往往将文本、语音输入和实时通话割裂实现，状态同步与链路切换成本较高。",
    "通用模型缺少私有知识支撑，面对项目资料型问题时回答容易停留在泛化表述。",
  ], { x: 0.85, y: 4.65, w: 6.05, h: 1.7, fontSize: 16.5 });
  addCard(slide, 7.35, 1.78, 5.05, 1.15, "交互层不足", "语音体验不连续，打断响应和交互节奏仍不理想。", "F9FCFF");
  addCard(slide, 7.35, 3.02, 5.05, 1.15, "知识层不足", "缺少私有资料支撑，资料型问答的针对性和可靠性不足。", "F9FCFF");
  addCard(slide, 7.35, 4.26, 5.05, 1.15, "工程层不足", "链路与配置缺少统一组织，维护、替换与扩展成本较高。", "F9FCFF");
  addCard(slide, 7.35, 5.50, 5.05, 0.95, "本课题意义", "围绕统一运行时构建多模态语音对话系统，为论文研究与工程落地提供可验证样本。", "FFF8E8");
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
    ["论文验证与结果分析", "通过真实页面、测试用例与链路结果分析系统效果。"] ,
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
  slide.addImage({ path: A.architecture, ...imageSizingContain(A.architecture, 0.45, 1.55, 8.95, 5.15) });
  addCaption(slide, "系统总体架构图", 1.25, 6.52, 7.2);
  addCard(slide, 9.65, 1.78, 3.0, 1.18, "前端交互层", "负责聊天交互、语音输入、实时通话和状态呈现。");
  addCard(slide, 9.65, 3.15, 3.0, 1.18, "后端编排层", "统一暴露接口并组织知识检索、模型调用与链路执行。");
  addCard(slide, 9.65, 4.52, 3.0, 1.18, "数据与服务层", "负责会话存储、向量检索以及外部模型与语音服务接入。");
  finalizeSlide(slide, "系统总体架构");
}

// 5 核心功能模块
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "核心功能模块", "功能设计围绕用户侧交互能力与系统侧配置能力展开");
  slide.addImage({ path: A.modules, ...imageSizingContain(A.modules, 0.45, 1.6, 7.6, 5.0) });
  addCaption(slide, "系统功能模块图", 1.3, 6.5, 5.9);
  addCard(slide, 8.35, 1.8, 4.1, 2.05, "用户侧能力", "文本对话、语音输入、实时通话和知识问答，面向实际交互场景提供连续体验。", "F9FCFF");
  addCard(slide, 8.35, 4.05, 4.1, 2.05, "系统侧能力", "Provider、链路、人格、音色、知识库与系统设置共同支撑系统可维护性。", "F9FCFF");
  finalizeSlide(slide, "核心功能模块");
}

// 6 关键设计一：统一会话运行时
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计一：统一会话运行时", "将文本对话、语音输入和实时通话纳入同一运行时模型");
  slide.addImage({ path: A.runtimeAi, ...imageSizingContain(A.runtimeAi, 6.95, 1.5, 5.7, 4.8) });
  addSectionChip(slide, "核心思想", 0.85, 1.45);
  addBulletList(slide, [
    "统一状态：集中管理会话标识、运行状态、转写文本和消息流。",
    "统一事件：以一致的事件模型驱动页面更新，减少多链路并行时的状态分散问题。",
    "统一扩展入口：把文本、语音输入和实时通话抽象成统一接口，便于切换、替换与扩展。",
  ], { x: 0.9, y: 1.95, w: 5.55, h: 3.3, fontSize: 17 });
  addCard(slide, 0.92, 5.75, 1.45, 0.78, "状态", "待机、监听、思考、播报");
  addCard(slide, 2.48, 5.75, 1.45, 0.78, "消息", "会话流与转写文本");
  addCard(slide, 4.04, 5.75, 1.45, 0.78, "指标", "首字延迟、总耗时等");
  addCard(slide, 5.60, 5.75, 1.45, 0.78, "事件", "统一分发与订阅");
  finalizeSlide(slide, "统一会话运行时");
}

// 7 关键设计二：双语音链路
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计二：双语音链路", "保留两条语音链路，是为了兼顾实时体验与工程可控性");
  addCard(slide, 0.78, 1.62, 5.7, 1.72, "分阶段语音链路", "适用场景：调试、实验分析与链路替换。\n优势：模块边界清晰，便于定位问题与独立替换。\n局限：交互节奏相对更慢。", "F9FCFF");
  addCard(slide, 6.86, 1.62, 5.7, 1.72, "一体化实时语音链路", "适用场景：连续通话与实时交互。\n优势：时延更低，可插话、可打断，体验更自然。\n局限：对网络环境和服务协同要求更高。", "F9FCFF");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.9, y: 3.58, w: 11.9, h: 0.54, rectRadius: 0.06,
    fill: { color: "FFF8E8" }, line: { color: "F2D7A2", pt: 1 },
  });
  slide.addText("设计结论：两条语音链路分别面向不同场景，前者强调可控性，后者强调实时性，可按业务目标灵活切换。", {
    x: 1.12, y: 3.73, w: 11.4, h: 0.18,
    fontFace: "Microsoft YaHei", fontSize: 12, bold: true, color: C.navy, margin: 0, align: "center",
  });
  slide.addImage({ path: A.voiceFlow, ...imageSizingContain(A.voiceFlow, 0.82, 4.32, 5.75, 2.18) });
  slide.addImage({ path: A.realtimeSeq, ...imageSizingContain(A.realtimeSeq, 6.78, 4.32, 5.75, 2.18) });
  addCaption(slide, "分阶段语音交互流程图", 1.18, 6.58, 5.0);
  addCaption(slide, "实时语音通话时序图", 7.18, 6.58, 5.0);
  finalizeSlide(slide, "双语音链路");
}

// 8 关键设计三：RAG 知识增强
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "关键设计三：RAG知识增强", "RAG：检索增强生成，用于提升资料型问答的针对性与可靠性");
  slide.addImage({ path: A.rag, ...imageSizingContain(A.rag, 6.6, 1.6, 6.0, 4.8) });
  addSectionChip(slide, "方法流程", 0.85, 1.48);
  addCard(slide, 0.9, 1.95, 5.1, 0.82, "步骤1 问题输入", "系统接收文本问题或由语音识别转写后的问题。", "FFFFFF");
  addCard(slide, 0.9, 2.88, 5.1, 0.82, "步骤2 检索门控", "先判断是否需要知识增强，避免每轮都无差别触发检索。", "FFFFFF");
  addCard(slide, 0.9, 3.81, 5.1, 0.82, "步骤3 召回与重排序", "从知识库切片中筛选相关内容，构造高质量知识上下文。", "FFFFFF");
  addCard(slide, 0.9, 4.74, 5.1, 0.82, "步骤4 上下文注入", "把知识片段与会话历史共同注入模型，生成更贴近资料的回答。", "FFFFFF");
  addCard(slide, 0.9, 5.72, 5.1, 0.68, "作用结论", "该方法主要用于提升资料型问答的针对性与可靠性。", "FFF8E8");
  finalizeSlide(slide, "RAG知识增强");
}

// 9 数据库与数据设计
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "数据库与数据设计", "数据库设计围绕会话、配置、知识和审计四类数据展开");
  slide.addImage({ path: A.databaseEr, ...imageSizingContain(A.databaseEr, 0.55, 1.5, 8.7, 5.55) });
  addCaption(slide, "数据库 E-R 图", 2.2, 6.88, 4.8);
  addCard(slide, 9.4, 1.7, 3.0, 1.1, "会话与消息", "保存会话标题、消息内容、消息类型与交互历史。");
  addCard(slide, 9.4, 2.95, 3.0, 1.1, "上下文记忆", "维护短期记忆、中期摘要和长期向量记忆。");
  addCard(slide, 9.4, 4.20, 3.0, 1.1, "Provider 与模型目录", "统一记录模型服务地址、模型清单和可用状态。");
  addCard(slide, 9.4, 5.45, 3.0, 1.1, "知识与审计", "保存知识库、文档切片、向量内容与链路审计记录。");
  finalizeSlide(slide, "数据库与数据设计");
}

// 10 系统实现与界面展示（一）
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统实现与界面展示（一）", "将原来过于密集的四图拼页拆开，优先保证投屏可读性");
  addScreenshotPanel(slide, A.chat, 0.82, 1.55, 5.85, 4.95, "聊天中心页面", "负责主对话、运行状态切换和实时语音交互展示。");
  addScreenshotPanel(slide, A.provider, 6.68, 1.55, 5.85, 4.95, "厂商与模型管理页面", "负责 Provider 配置、连通性测试和模型目录维护。");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 1.15, y: 6.72, w: 11.05, h: 0.42, rectRadius: 0.05,
    fill: { color: "FFF8E8" }, line: { color: "F2D7A2", pt: 1 },
  });
  slide.addText("这两个页面对应系统的主要交互入口和模型服务管理入口，适合在答辩中直接展示真实实现效果。", {
    x: 1.35, y: 6.84, w: 10.65, h: 0.16,
    fontFace: "Microsoft YaHei", fontSize: 11, color: C.navy, margin: 0, align: "center", bold: true,
  });
  finalizeSlide(slide, "系统实现与界面展示（一）");
}

// 11 系统实现与界面展示（二）
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统实现与界面展示（二）", "继续展示知识库与音色等更具代表性的功能页面");
  addScreenshotPanel(slide, A.knowledge, 0.82, 1.55, 5.85, 4.95, "知识库管理页面", "负责文档上传、切片解析、检索测试和参数维护。");
  addScreenshotPanel(slide, A.voice, 6.68, 1.55, 5.85, 4.95, "音色管理页面", "负责音色列表、样本上传、试听和音色克隆。");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 1.15, y: 6.72, w: 11.05, h: 0.42, rectRadius: 0.05,
    fill: { color: "EEF8F8" }, line: { color: "B9E3DE", pt: 1 },
  });
  slide.addText("这两个页面说明系统不仅关注对话过程，还把私有资料处理与个性化语音能力纳入同一平台。", {
    x: 1.35, y: 6.84, w: 10.65, h: 0.16,
    fontFace: "Microsoft YaHei", fontSize: 11, color: C.navy, margin: 0, align: "center", bold: true,
  });
  finalizeSlide(slide, "系统实现与界面展示（二）");
}

// 12 系统测试与结果分析
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "系统测试与结果分析", "将核心测试结果整理为更适合投屏阅读的表格与结论卡片");
  const rows = [
    ["测试项目", "观察结果", "结论"],
    ["文本对话功能测试", "会话创建、消息保存和回复生成链路可稳定完成。", "通过"],
    ["实时通话链路测试", "支持持续传输、局部转写、语音播报和插话打断。", "通过"],
    ["知识库开启/关闭对比", "资料型问答在开启知识库后更具体，也更贴近文档内容。", "有效"],
    ["音色样本上传与异常处理", "成功路径与错误路径均能给出明确反馈。", "通过"],
  ];
  const colXs = [0.78, 3.50, 10.55];
  const colWs = [2.55, 6.95, 1.70];
  const rowY = 1.68;
  const rowH = 0.74;
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
        fontSize: rIdx === 0 ? 12 : 11.5,
        bold: rIdx === 0,
        color: rIdx === 0 ? C.white : C.text,
        align: cIdx === 1 ? "left" : "center",
        valign: "mid",
        margin: 0,
      });
    });
  });
  addCard(slide, 0.82, 5.58, 3.85, 1.0, "结论1 功能闭环验证", "系统核心功能已完成闭环验证，主要设计内容能够落地实现。", "F9FCFF");
  addCard(slide, 4.78, 5.58, 3.85, 1.0, "结论2 场景适配性", "双链路设计具备场景适配性，可支持不同交互需求下的方案选择。", "F9FCFF");
  addCard(slide, 8.74, 5.58, 3.78, 1.0, "结论3 外部条件影响", "系统表现仍受网络环境、浏览器能力和模型服务稳定性影响。", "FFF8E8");
  finalizeSlide(slide, "系统测试与结果分析");
}

// 13 论文特色与设计亮点
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "论文特色与设计亮点", "从答辩视角概括最值得老师记住的三项核心设计");
  addCard(slide, 0.85, 1.75, 3.75, 3.95, "亮点一 统一会话运行时", "将文本对话、语音输入和实时通话纳入同一运行时，统一管理状态、消息流、事件和指标，降低了多交互方式并行时的状态割裂问题。", "FFFFFF");
  addCard(slide, 4.80, 1.75, 3.75, 3.95, "亮点二 双语音链路设计", "同时保留分阶段语音链路和一体化实时语音链路，在工程可控性与实时体验之间形成互补，能够覆盖调试分析与真实通话两类场景。", "FFFFFF");
  addCard(slide, 8.75, 1.75, 3.75, 3.95, "亮点三 知识与个性化闭环", "把 RAG 知识增强、记忆管理、人格配置和音色管理纳入同一系统，形成从问答能力到个性化体验的完整功能闭环。", "FFFFFF");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 1.15, y: 6.05, w: 11.0, h: 0.48, rectRadius: 0.05,
    fill: { color: "EEF8F8" }, line: { color: "B9E3DE", pt: 1 },
  });
  slide.addText("答辩时可将这一页作为总结页使用，帮助评审快速抓住本论文相较于普通聊天系统的差异化设计。", {
    x: 1.35, y: 6.19, w: 10.6, h: 0.18,
    fontFace: "Microsoft YaHei", fontSize: 11, color: C.navy, margin: 0, align: "center", bold: true,
  });
  finalizeSlide(slide, "论文特色与设计亮点");
}

// 14 结论与展望
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "结论与展望", "完成了从架构、实现到测试的完整闭环");
  addSectionChip(slide, "结论", 0.85, 1.45);
  addBulletList(slide, [
    "已实现一个支持文本、语音输入、实时语音通话和知识增强的多模态智能语音聊天机器人系统。",
    "论文围绕统一会话运行时、双语音链路和RAG知识增强完成了系统设计与实现目标。",
    "通过真实页面、测试用例和链路验证，说明系统具备较好的可实现性、可验证性和工程可控性。",
  ], { x: 0.9, y: 1.95, w: 5.65, h: 3.2, fontSize: 17 });
  addSectionChip(slide, "展望", 7.0, 1.45, "EEF8F8");
  addCard(slide, 7.0, 1.95, 5.2, 0.9, "方向1 识别稳定性", "进一步优化复杂噪声环境下的语音识别鲁棒性。", "FFFFFF");
  addCard(slide, 7.0, 3.0, 5.2, 0.9, "方向2 长时对话能力", "增强长期记忆召回与多轮调度策略，提高连续对话一致性。", "FFFFFF");
  addCard(slide, 7.0, 4.05, 5.2, 0.9, "方向3 多模态扩展", "拓展图像理解或更丰富的多模态输入输出能力。", "FFFFFF");
  slide.addImage({ path: A.interrupt, ...imageSizingContain(A.interrupt, 8.0, 5.12, 3.55, 1.45) });
  finalizeSlide(slide, "结论与展望");
}

// 15 致谢
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
