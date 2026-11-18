import os
import json
import smtplib
import datetime
import requests
from email.mime.text import MIMEText
from email.header import Header

# 2026年下半年六级考试日期：2026年12月12日（考完次日自动停止推送）
EXAM_DATE = datetime.date(2026, 12, 12)

# 工作日复习计划（每天约 35-45 分钟）
WEEKDAY_PLAN = {
    0: ["🎧 <b>真题听力（20分钟）：</b>精听 1 篇六级真题长对话，重点听转折词（but/however）后面的答案句", "📖 <b>真题阅读（15分钟）：</b>做 1 篇仔细阅读真题，只求弄懂错题的同义替换"],
    1: ["✍️ <b>真题微翻译（15分钟）：</b>只翻今天推送的这 1 句真题核心句，对照采分点批改", "📖 <b>真题匹配（15分钟）：</b>做 1 篇段落信息匹配真题，练习找关键词定位"],
    2: ["🎧 <b>真题听力（20分钟）：</b>精听 1 篇六级讲座真题（Section C），抓前三句主旨", "📖 <b>真题阅读（15分钟）：</b>做 1 篇仔细阅读真题，圈出不认识的真题熟词僻义"],
    3: ["📝 <b>写作积累（15分钟）：</b>背诵 2 个六级真题万能开头/过渡句型", "📖 <b>真题阅读（15分钟）：</b>做 1 篇仔细阅读真题，拆解 1 个长难句"],
    4: ["🎧 <b>考场手感（25分钟）：</b>倍速重听本周听过的真题音频，培养语感", "✍️ <b>查漏补缺（10分钟）：</b>快速浏览本周打卡过的真题高频词"]
}

# 周末减负计划（每天仅需 5-10 分钟，防放弃轻松模式！）
WEEKEND_PLAN = {
    5: ["☕ <b>周六轻松保温（仅需5分钟）：</b>今天不用刷题！躺在床上看完下方 AI 为你挑的 <b>2个真题必考词 + 1个万能句型</b> 就算打卡成功，放心去休息！"],
    6: ["🌿 <b>周日无痛唤醒（仅需5分钟）：</b>今天依然不刷套卷！花 5 分钟扫一眼下方的真题救命考点，保持一点点英语语感即可，拒绝焦虑！"]
}

def call_gemini_ai(is_weekend, days_left, today_str):
    """调用 Google AI Studio (Gemini API) 生成每日真题内容"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    if is_weekend:
        prompt = f"""
        今天是 {today_str}（周末减负模式），距离2026年12月12日英语六级考试还有 {days_left} 天。
        为了防止学生周末因为想休息而放弃复习，请生成一份【5分钟就能看完的极简六级真题保温卡片】（直接输出美观的 HTML 片段，不要包含 ```html 标记）：
        1. 【周末2个真题救命词】：挑2个六级真题里最高频的“熟词僻义”或核心词（带音标、真题常考义、1句极简真题短例句）。
        2. 【1组阅读必考同义替换】：给出一组六级阅读最爱考的同义词替换链（3-4个词）。
        3. 【周末1个写作/翻译万能公式】：给1个六级考场上直接能套用的高分句型（带中英对照）。
        排版要求：多用鼓励、轻松的语气，使用柔和的浅色背景块（内联 CSS），重点词加粗标亮。
        """
    else:
        prompt = f"""
        今天是 {today_str}（工作日冲刺模式），距离2026年12月12日英语六级考试还有 {days_left} 天。
        请严格基于【历年英语六级（CET-6）真题与核心考点】，生成今日的复习内容（直接输出美观的 HTML 片段，不要包含 ```html 标记）：
        1. 【考点一：3个六级真题高频词/熟词僻义】：包含音标、真题常考词义（特别标出容易踩坑的熟词僻义）、真题常见搭配。
        2. 【考点二：1组阅读/听力高频同义替换链】：展示六级出题人如何改写原文词汇。
        3. 【考点三：1道六级仔细阅读真题长难句拆解】：给出真题原句，并使用 <details><summary>👉 点击查看语法骨架拆解与译文</summary>...</details> 折叠解析和参考译文。
        4. 【考点四：1句六级历年翻译真题实战】：给出中文真题原句和【阅卷采分点提示】，并使用 <details><summary>👉 自己想完后，点击展开满分参考译文</summary>...</details> 折叠英文参考译文。
        排版要求：使用清晰的内联 CSS 样式，模块分明，重点突出，适合在手机微信和邮箱中阅读。
        """

    # 优先调用 gemini-2.5-flash，备用 gemini-2.0-flash
    for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7}
        }
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                # 清理可能残留的代码块标记
                text = text.replace("```html", "").replace("```", "").strip()
                return text
            else:
                print(f"模型 {model} 返回状态码 {res.status_code}: {res.text}")
        except Exception as e:
            print(f"调用 {model} 异常: {e}")
    return None

def fallback_content(is_weekend, day_idx):
    """内置真题兜底库（当未配置或未连上 API 时自动启用）"""
    words = [
        ("address /əˈdres/", "v. 解决、应对（问题）", "address the crisis（解决危机，替换 solve / tackle）"),
        ("compromise /ˈkɒmprəmaɪz/", "v. 损害，危及；妥协", "compromise safety（损害安全，替换 jeopardize）"),
        ("imperative /ɪmˈperətɪv/", "adj. 至关重要的，急需的", "It is imperative that...（做……是当务之急）"),
        ("vulnerable /ˈvʌlnərəbl/", "adj. 脆弱的，易受伤害的", "be vulnerable to climate change（易受气候变化影响）"),
        ("scrutiny /ˈskruːtəni/", "n. 仔细审查，严密监督", "come under close scrutiny（受到严格审查）"),
        ("alleviate /əˈliːvieɪt/", "v. 减轻，缓解（痛苦/贫困）", "alleviate poverty（缓解贫困，反义词 aggravate 恶化）")
    ]
    w1, w2 = words[day_idx % len(words)], words[(day_idx + 1) % len(words)]
    if is_weekend:
        return f"""
        <div style="background:#f0fff4; padding:12px; border-radius:6px; border:1px solid #c6f6d5;">
            <h4 style="margin:0 0 8px 0; color:#276749;">🌱 周末2个真题救命词（扫一眼就行）</h4>
            <p style="margin:4px 0;"><b>1. {w1[0]}</b>：{w1[1]} <br><span style="color:#666;font-size:0.9em;">真题搭配：{w1[2]}</span></p>
            <p style="margin:4px 0;"><b>2. {w2[0]}</b>：{w2[1]} <br><span style="color:#666;font-size:0.9em;">真题搭配：{w2[2]}</span></p>
        </div>
        """
    return f"""
    <div style="background:#f7fafc; padding:12px; border-radius:6px; border:1px solid #e2e8f0;">
        <h4 style="margin:0 0 8px 0; color:#2b6cb0;">🔑 今日真题高频熟词僻义</h4>
        <p style="margin:4px 0;"><b>1. {w1[0]}</b>：{w1[1]}（{w1[2]}）</p>
        <p style="margin:4px 0;"><b>2. {w2[0]}</b>：{w2[1]}（{w2[2]}）</p>
    </div>
    """

def build_daily_message():
    tz_bj = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_bj).date()
    days_left = (EXAM_DATE - today).days

    # 1. 如果已经过了今年的六级考试日，直接返回 None，停止推送！
    if days_left < 0:
        print("🎉 2026年12月六级考试已结束，自动停止每日推送！")
        return None, None

    # 2. 如果是考试当天（2026-12-12），发送专属考前祝福与救急锦囊
    if days_left == 0:
        title = "🔥 今天六级开考！考前终极抢分锦囊 & 必过祝福"
        html = """
        <div style="font-family: sans-serif; line-height: 1.6; padding: 15px; background: #fffaf0; border: 2px solid #dd6b20; border-radius: 8px;">
            <h2 style="color: #c05621; margin-top: 0;">🎉 终于等到今天！祝你下午六级考的全会、蒙的全对！</h2>
            <p><b>⏰ 下午入场前最后叮嘱：</b></p>
            <ul>
                <li>检查证件：<b>准考证、身份证、学生证、调频耳机（及备用电池）、2B铅笔、黑色签字笔</b>。</li>
                <li><b>写作救急句：</b><code>It is universally acknowledged that...</code> / <code>Only by taking joint efforts can we...</code></li>
                <li><b>听力口诀：</b>视听一致抓主干，听到 <code>but / however / actually / in fact</code> 立刻竖起耳朵，答案就在后面！</li>
            </ul>
            <p style="color: #718096; font-size: 0.9em;">（这是本机器人的最后一条推送，考完好好休息，静候高分佳音！）</p>
        </div>
        """
        return title, html

    # 3. 正常备考日：判断是否为周末（周六=5，周日=6）
    weekday_idx = today.weekday()
    is_weekend = weekday_idx in (5, 6)
    day_idx = today.timetuple().tm_yday

    mode_tag = "☕ 周末减负保温" if is_weekend else "📘 工作日真题特训"
    title = f"{mode_tag} | 六级倒计时 {days_left} 天 ({today.strftime('%m-%d')})"
    tasks = WEEKEND_PLAN[weekday_idx] if is_weekend else WEEKDAY_PLAN[weekday_idx]

    # 调用 Google Gemini AI 生成真题内容（若失败则用兜底真题库）
    ai_html = call_gemini_ai(is_weekend, days_left, today.strftime("%Y-%m-%d"))
    if not ai_html:
        ai_html = fallback_content(is_weekend, day_idx)

    header_bg = "linear-gradient(135deg, #38a169, #276749)" if is_weekend else "linear-gradient(135deg, #2b6cb0, #2c5282)"
    sub_tip = "周末不内卷！花 5 分钟扫一眼就算打卡成功，留出精力好好休息~" if is_weekend else "全部考点源自历年六级真题 · 每天稳扎稳打拿下一分"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.65; color: #2d3748; max-width: 650px;">
        <div style="background: {header_bg}; color: white; padding: 14px 18px; border-radius: 8px; margin-bottom: 16px;">
            <h2 style="margin: 0; font-size: 1.2em;">🎯 {mode_tag} | 距今年六级还有 <span style="color: #fbd38d; font-size: 1.25em;">{days_left}</span> 天</h2>
            <p style="margin: 4px 0 0 0; font-size: 0.85em; opacity: 0.92;">{sub_tip}</p>
        </div>

        <h3 style="color: #2d3748; border-left: 4px solid #4a5568; padding-left: 8px; margin-bottom: 8px;">📌 今日任务安排</h3>
        <ul style="padding-left: 20px; margin-top: 6px;">
            {''.join(f'<li style="margin-bottom: 6px;">{t}</li>' for t in tasks)}
        </ul>

        <hr style="border: none; border-top: 1px dashed #cbd5e0; margin: 14px 0;">
        {ai_html}
    </div>
    """
    return title, html

def push_wechat(title, html):
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        return
    res = requests.post("http://www.pushplus.plus/send", json={
        "token": token, "title": title, "content": html, "template": "html"
    }, timeout=15)
    print("微信推送结果:", res.text)

def push_email(title, html):
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    receiver = os.environ.get("EMAIL_RECEIVER") or sender
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    if not (sender and password):
        return
    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = Header(f"六级AI督学 <{sender}>", "utf-8")
    msg["To"] = Header(receiver, "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    with smtplib.SMTP_SSL(smtp_server, 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
    print("邮箱推送成功！")

if __name__ == "__main__":
    title, html = build_daily_message()
    if title and html:
        push_wechat(title, html)
        push_email(title, html)
