from pathlib import Path


PPT_JS = Path(r"D:\AgentLearning\chatBot\output\ppt\build_thesis_defense_ppt.js")
text = PPT_JS.read_text(encoding="utf-8")


def replace_between(src: str, start_marker: str, end_marker: str, replacement_body: str) -> str:
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[:start] + replacement_body + "\n\n" + src[end:]


helper_anchor = """function finalizeSlide(slide, shortTitle) {
  addFooter(slide, shortTitle);
  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}
"""

helper_insert = helper_anchor + """

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
"""

if "function addScreenshotPanel(" not in text:
    text = text.replace(helper_anchor, helper_insert, 1)

block7 = """// 7 鍏抽敭璁捐浜岋細鍙岃闊抽摼璺?
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "鍏抽敭璁捐浜岋細鍙岃闊抽摼璺?", "淇濈暀鍙岄摼璺笉鏄噸澶嶅疄鐜帮紝鑰屾槸涓轰簡鍏奸【瀹炴椂浣撻獙鍜屽伐绋嬪彲鎺ф€?");
  addCard(slide, 0.78, 1.62, 5.55, 1.72, "鍒嗛樁娈佃闊抽摼璺?", "閫傜敤鍦烘櫙锛氳皟璇曘€佸疄楠屽垎鏋愪笌閾捐矾鏇挎崲銆俓n浼樺娍锛氭ā鍧楄竟鐣屾竻鏅帮紝鍙帶鎬у己銆俓n灞€闄愶細浜や簰鑺傚鐩稿杈冩參銆?", "F9FCFF");
  addCard(slide, 7.02, 1.62, 5.55, 1.72, "涓€浣撳寲瀹炴椂璇煶閾捐矾", "閫傜敤鍦烘櫙锛氳繛缁€氳瘽涓庡疄鏃朵氦浜掋€俓n浼樺娍锛氫綆鏃跺欢銆佸彲鎻掕瘽銆佷綋楠岃嚜鐒躲€俓n灞€闄愶細瀵圭綉缁滃拰鏈嶅姟鍗忓悓瑕佹眰鏇撮珮銆?", "F9FCFF");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.9, y: 3.58, w: 11.9, h: 0.54, rectRadius: 0.06,
    fill: { color: "FFF8E8" }, line: { color: "F2D7A2", pt: 1 },
  });
  slide.addText("璁捐缁撹锛氬弻璇煶閾捐矾闈㈠悜涓嶅悓鍦烘櫙鍒嗗埆浼樺厛淇濊瘉鍙帶鎬у拰瀹炴椂鎬э紝鍏蜂綋閫夋嫨鍙殢涓氬姟鐩爣鍒囨崲銆?", {
    x: 1.12, y: 3.73, w: 11.4, h: 0.18,
    fontFace: "Microsoft YaHei", fontSize: 12, bold: true, color: C.navy, margin: 0, align: "center",
  });
  slide.addImage({ path: A.voiceFlow, ...imageSizingContain(A.voiceFlow, 0.82, 4.38, 5.75, 2.1) });
  slide.addImage({ path: A.realtimeSeq, ...imageSizingContain(A.realtimeSeq, 6.78, 4.38, 5.75, 2.1) });
  addCaption(slide, "鍒嗛樁娈佃闊充氦浜掓祦绋?", 1.18, 6.58, 5.0);
  addCaption(slide, "瀹炴椂璇煶閫氳瘽鏃跺簭鍥?", 7.18, 6.58, 5.0);
  finalizeSlide(slide, "鍙岃闊抽摼璺?");
}"""

block9 = """// 9 鏁版嵁搴撲笌鏁版嵁璁捐
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "鏁版嵁搴撲笌鏁版嵁璁捐", "鏁版嵁搴撹璁″洿缁曚細璇濄€侀厤缃€佺煡璇嗗拰瀹¤鍥涚被鏁版嵁灞曞紑");
  slide.addImage({ path: A.databaseEr, ...imageSizingContain(A.databaseEr, 0.6, 1.55, 8.45, 5.45) });
  addCaption(slide, "鏁版嵁搴?E-R 鍥?", 2.0, 6.82, 4.9);
  addCard(slide, 9.25, 1.75, 3.25, 1.08, "浼氳瘽涓庢秷鎭?", "淇濆瓨浼氳瘽鏍囬銆佹秷鎭唴瀹广€佸唴瀹圭被鍨嬪拰浜や簰鍘嗗彶銆?");
  addCard(slide, 9.25, 2.98, 3.25, 1.08, "涓婁笅鏂囪蹇?", "缁存姢鐭湡璁板繂銆佷腑鏈熸憳瑕佸拰闀挎湡鍚戦噺璁板繂銆?");
  addCard(slide, 9.25, 4.21, 3.25, 1.08, "Provider 涓庢ā鍨嬬洰褰?", "缁熶竴淇濆瓨妯″瀷鏈嶅姟鍦板潃銆佹ā鍨嬫竻鍗曞拰鐘舵€佷俊鎭€?");
  addCard(slide, 9.25, 5.44, 3.25, 1.08, "鐭ヨ瘑涓庡璁?", "淇濆瓨鐭ヨ瘑搴撱€佹枃妗ｅ垏鐗囥€佸悜閲忓唴瀹逛笌閾捐矾瀹¤璁板綍銆?");
  finalizeSlide(slide, "鏁版嵁搴撲笌鏁版嵁璁捐");
}"""

block10 = """// 10 绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙涓€锛?
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙涓€锛?", "鎶婂師鏉ユ墍鏈夌晫闈㈡嫾鍦ㄤ竴椤电殑鍐呭鎷嗗紑锛屼紭鍏堜繚璇佹姇灞忓彲璇绘€?");
  addScreenshotPanel(slide, A.chat, 0.82, 1.55, 5.85, 4.95, "鑱婂ぉ涓績椤甸潰", "璐熻矗涓诲璇濄€佽繍琛岀姸鎬佸垏鎹㈠拰瀹炴椂璇煶浜や簰灞曠ず銆?");
  addScreenshotPanel(slide, A.provider, 6.68, 1.55, 5.85, 4.95, "鍘傚晢涓庢ā鍨嬬鐞?", "璐熻矗 Provider 閰嶇疆銆佽繛閫氭€ф祴璇曞拰妯″瀷鐩綍缁存姢銆?");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 1.15, y: 6.72, w: 11.05, h: 0.42, rectRadius: 0.05,
    fill: { color: "FFF8E8" }, line: { color: "F2D7A2", pt: 1 },
  });
  slide.addText("杩欎袱涓〉闈㈠搴斾簡绯荤粺鐨勪富浜や簰鍏ュ彛鍜屾ā鍨嬫湇鍔＄鐞嗗叆鍙ｏ紝鏄瓟杈╂椂鏈€閫傚悎灞曠ず鐨勭湡瀹炲疄鐜扮晫闈€?", {
    x: 1.35, y: 6.84, w: 10.65, h: 0.16,
    fontFace: "Microsoft YaHei", fontSize: 11, color: C.navy, margin: 0, align: "center", bold: true,
  });
  finalizeSlide(slide, "绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙涓€锛?");
}"""

block11 = """// 11 绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙浜岋級
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙浜岋級", "缁х画灞曠ず鐭ヨ瘑搴撲笌闊宠壊绛夋洿鍏蜂唬琛ㄦ€х殑鍔熻兘椤甸潰");
  addScreenshotPanel(slide, A.knowledge, 0.82, 1.55, 5.85, 4.95, "鐭ヨ瘑搴撶鐞嗛〉闈?", "璐熻矗鏂囨。涓婁紶銆佸垏鐗囪В鏋愩€佹绱㈡祴璇曞拰鍙傛暟缁存姢銆?");
  addScreenshotPanel(slide, A.voice, 6.68, 1.55, 5.85, 4.95, "闊宠壊绠＄悊椤甸潰", "璐熻矗闊宠壊鍒楄〃銆佹牱鏈笂浼犮€佽瘯鍚拰闊宠壊鍏嬮殕銆?");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 1.15, y: 6.72, w: 11.05, h: 0.42, rectRadius: 0.05,
    fill: { color: "EEF8F8" }, line: { color: "B9E3DE", pt: 1 },
  });
  slide.addText("杩欎袱涓〉闈㈣鏄庣郴缁熶笉浠呭叧娉ㄥ璇濓紝杩樺皢绉佹湁璧勬枡鍜屼釜鎬у寲璇煶鑳藉姏绾冲叆鍚屼竴濂楀钩鍙般€?", {
    x: 1.35, y: 6.84, w: 10.65, h: 0.16,
    fontFace: "Microsoft YaHei", fontSize: 11, color: C.navy, margin: 0, align: "center", bold: true,
  });
  finalizeSlide(slide, "绯荤粺瀹炵幇涓庣晫闈㈠睍绀猴紙浜岋級");
}"""

block12 = """// 12 绯荤粺娴嬭瘯涓庣粨鏋滃垎鏋?
{
  const slide = pptx.addSlide("AHUT_MASTER");
  addTitle(slide, "绯荤粺娴嬭瘯涓庣粨鏋滃垎鏋?", "鎶婃牳蹇冩祴璇曠粨鏋滄敹鏁翠负涓€椤垫洿鏄撴姇灞忛槄璇荤殑琛ㄦ牸");
  const rows = [
    ["娴嬭瘯椤?", "瑙傚療缁撴灉", "缁撹"],
    ["鏂囨湰瀵硅瘽鍔熻兘娴嬭瘯", "浼氳瘽鍒涘缓銆佹秷鎭繚瀛樺拰鍥炲鐢熸垚鍙互绋冲畾瀹屾垚銆?", "閫氳繃"],
    ["瀹炴椂閫氳瘽閾捐矾娴嬭瘯", "鏀寔鎸佺画浼犺緭銆佸眬閮ㄨ浆鍐欍€佹挱鎶ュ拰鎻掕瘽鎵撴柇銆?", "閫氳繃"],
    ["鐭ヨ瘑搴撳紑鍚?鍏抽棴瀵规瘮", "璧勬枡鍨嬮棶绛斿湪寮€鍚煡璇嗗簱鍚庢洿鍏蜂綋銆佹洿璐磋繎鏂囨。銆?", "鏈夋晥"],
    ["闊宠壊鏍锋湰涓婁紶涓庡紓甯稿鐞?", "鍏嬮殕鎴愬姛璺緞涓庨敊璇矾寰勫潎鏈夋槑纭弽棣堛€?", "閫氳繃"],
  ];
  const colXs = [0.78, 3.55, 10.72];
  const colWs = [2.65, 6.95, 1.28];
  const rowY = 1.68;
  const rowH = 0.7;
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
        fontSize: rIdx === 0 ? 11.5 : 11,
        bold: rIdx === 0,
        color: rIdx === 0 ? C.white : C.text,
        align: cIdx === 1 ? "left" : "center",
        valign: "mid",
        margin: 0,
      });
    });
  });
  addCard(slide, 0.82, 5.52, 3.8, 1.08, "缁撹1 鍔熻兘闂幆楠岃瘉", "绯荤粺鏍稿績鍔熻兘宸插畬鎴愰棴鐜獙璇侊紝璇存槑涓昏璁捐鍐呭宸茶惤鍦般€?", "F9FCFF");
  addCard(slide, 4.80, 5.52, 3.8, 1.08, "缁撹2 鍦烘櫙閫傞厤鎬?", "鍙岄摼璺璁″叿澶囧満鏅€傞厤鎬э紝鑳藉鏀拺涓嶅悓浜や簰闇€姹備笅鐨勬柟妗堥€夋嫨銆?", "F9FCFF");
  addCard(slide, 8.78, 5.52, 3.74, 1.08, "缁撹3 澶栭儴鏉′欢褰卞搷", "绯荤粺浠嶅彈缃戠粶鐜銆佹祻瑙堝櫒鑳藉姏鍜屾ā鍨嬫湇鍔＄ǔ瀹氭€у奖鍝嶃€?", "FFF8E8");
  finalizeSlide(slide, "绯荤粺娴嬭瘯涓庣粨鏋滃垎鏋?");
}"""

text = replace_between(text, "// 7 ", "// 8 ", block7)
text = replace_between(text, "// 9 ", "// 10 ", block9)
text = replace_between(text, "// 10 ", "// 11 ", block10)
text = replace_between(text, "// 11 ", "// 12 ", block11)
text = replace_between(text, "// 12 ", "// 13 ", block12)
text = text.replace("// 13 缁撹涓庡睍鏈?", "// 14 缁撹涓庡睍鏈?")
text = text.replace("// 14 鑷磋阿", "// 15 鑷磋阿")
text = text.replace('slide.addImage({ path: A.interrupt, ...imageSizingContain(A.interrupt, 7.75, 5.25, 3.85, 1.25) });',
                    'slide.addImage({ path: A.interrupt, ...imageSizingContain(A.interrupt, 8.0, 5.12, 3.55, 1.45) });')

PPT_JS.write_text(text, encoding="utf-8")
print(PPT_JS)
