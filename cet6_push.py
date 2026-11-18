import os
import re
import time
import json
import smtplib
import datetime
import urllib.parse
import requests
from email.mime.text import MIMEText
from email.header import Header

# 2026年下半年六级考试日期：2026年12月12日（考完次日自动停止推送）
EXAM_DATE = datetime.date(2026, 12, 12)

def clean_for_tts(text):
    """清理特殊引号与换行符，确保句子语音接口 100% 正常合成"""
    text = text.replace("\n", " ").replace('"', "").replace("“", "").replace("”", "").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()

def split_sentences(script):
    """按句号、问号、感叹号切分自然句，供分句复盘精听使用"""
    clean_text = clean_for_tts(script)
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if s.strip()]
    return sents if sents else [clean_text]

def call_gemini_ai(is_weekend, days_left, today_str):
    """高速版 Google AI 调用函数（优先使用秒通模型，遇503秒切备用模型）"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    models_to_try = [
        "gemini-3-flash-preview",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.8-flash"
    ]

    if is_weekend:
        prompt = f"""
        今天是 {today_str}（周末5分钟减负模式），距离六级考试还有 {days_left} 天。
        请严格按以下 JSON 格式返回今日轻量真题保温内容（只输出纯 JSON，不要任何多余文字）：
        {{
          "words": [
            {{"word": "单词 /音标/", "meaning": "【真题熟词僻义】常考词义", "collocation": "真题搭配与同义替换"}},
            {{"word": "单词 /音标/", "meaning": "【真题高频】常考词义", "collocation": "真题搭配与同义替换"}}
          ],
          "listening": {{
            "script": "一段由2到3个简短句子组成的六级真题听力节选（总词数40-50词，中间包含 but 或 however 等转折考点，不要换行）",
            "question": "针对上述听力内容的1道六级标准英文设问？",
            "options": ["A) 选项A", "B) 选项B", "C) 选项C", "D) 选项D"],
            "analysis": "正确答案及解析（指出听力原文中哪个转折词或信号词引出了答案，并附原文中文翻译）"
          }},
          "reading": null,
          "translation": {{
            "source": "六级真题高频万能句型（周末保温）",
            "cn": "1句简短高频的六级翻译真题原句",
            "tips": "核心采分词与句型提示",
            "en": "标准英文参考译文"
          }}
        }}
        """
    else:
        prompt = f"""
        今天是 {today_str}（工作日真题实战模式），距离六级考试还有 {days_left} 天。
        请严格基于【历年英语六级（CET-6）真题】，生成一套包含【听力+阅读+翻译+核心词】的完整每日微真题卷。
        请严格按照以下 JSON 格式输出（只输出合法 JSON，不要包含 ```json 代码块标记）：
        {{
          "words": [
            {{"word": "单词1 /音标/", "meaning": "【真题熟词僻义/高频】词义", "collocation": "真题搭配及同义替换词"}},
            {{"word": "单词2 /音标/", "meaning": "【真题熟词僻义/高频】词义", "collocation": "真题搭配及同义替换词"}},
            {{"word": "单词3 /音标/", "meaning": "【真题熟词僻义/高频】词义", "collocation": "真题搭配及同义替换词"}}
          ],
          "listening": {{
            "script": "一段由3个清晰句子组成的六级真题听力短文或对话节选（总词数50-65词，必须包含 however, actually, in fact 等六级转折出题信号词，单段落无换行）",
            "question": "What does the speaker mainly imply / talk about ...? (1道标准六级听力英文提问)",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "analysis": "【正确答案】及【听音关键点】：指出原文哪句话、哪个信号词对应正确选项，并提供听力原文的中文译文。"
          }},
          "reading": {{
            "source": "六级仔细阅读真题精选（标明题材，如：科技与AI / 经济政策 / 环境生态 / 认知心理学）",
            "passage": "一段130-160词的六级仔细阅读真题核心段落（包含长难句与同义替换考点，可分1-2段）",
            "q1": "1. 第1道仔细阅读真题英文题干（细节题或推理题）",
            "q1_options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "q2": "2. 第2道仔细阅读真题英文题干（观点态度题或主旨/词义题）",
            "q2_options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "analysis": "【答案与同义替换精析】：分别解析第1题和第2题的正确答案，重点标出【正确选项是如何同义改写原文句子的】，并附上全文精准中文译文。"
          }},
          "translation": {{
            "source": "历年六级翻译真题（标明主题，如中国传统文化/科技创新/社会发展/地理工程）",
            "cn": "1句经典的六级真题翻译中文原句（约25-40字）",
            "tips": "💡 阅卷采分点：列出2-3个核心词组和推荐使用的句型结构",
            "en": "高分地道英文参考译文"
          }}
        }}
        """

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "responseMimeType": "application/json"
            }
        }
        try:
            res = requests.post(url, json=payload, timeout=40)
            if res.status_code == 200:
                print(f"✅ 成功调用 Google AI 模型: {model}！")
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            else:
                print(f"⏳ 模型 {model} 状态码 {res.status_code}，立即切换下一个模型...")
        except Exception as e:
            print(f"⏳ 模型 {model} 响应超时，立即切换下一个模型: {e}")
    return None

def get_fallback_data(is_weekend, day_idx):
    """内置完整真题库（极端断网情况下的全套兜底卷）"""
    return {
        "words": [
            {"word": "compromise /ˈkɒmprəmaɪz/", "meaning": "【真题熟词僻义】v. 损害，危及；妥协", "collocation": "compromise safety/quality（损害安全/质量，同义替换 jeopardize / undermine）"},
            {"word": "scrutiny /ˈskruːtəni/", "meaning": "【真题高频】n. 仔细审查，严密监督", "collocation": "come under close scrutiny（受到严格审查，同义替换 inspection / examination）"},
            {"word": "alleviate /əˈliːvieɪt/", "meaning": "【真题核心】v. 减轻，缓和（痛苦、贫困等）", "collocation": "alleviate poverty（缓解贫困，反义考点：aggravate / exacerbate 加剧）"}
        ],
        "listening": {
            "script": "Many people assume that working longer hours leads to higher productivity. However, recent studies across European countries reveal the exact opposite. Once employees exceed forty-five hours a week, their efficiency drops sharply due to mental fatigue.",
            "question": "What do recent studies reveal about working longer hours?",
            "options": [
                "A) It significantly boosts a company's overall profit.",
                "B) It actually reduces efficiency due to mental fatigue.",
                "C) It is widely welcomed by European employers.",
                "D) It helps employees develop stronger mental endurance."
            ],
            "analysis": "<b>【正确答案】B</b><br><b>【听音关键点】</b>注意听第2句开头转折信号词 <code>However</code> 以及第3句核心结果：<code>their efficiency drops sharply due to mental fatigue</code>（由于精神疲劳，效率急剧下降），B项中 <code>reduces efficiency</code> 同义替换原文 <code>efficiency drops</code>。<br><b>【原文译文】</b>许多人认为延长工作时间会提高生产力。然而，近期在欧洲多国开展的研究却揭示了完全相反的结果。一旦员工每周工作超过45小时，由于精神疲劳，他们的效率就会急剧下降。"
        },
        "reading": None if is_weekend else {
            "source": "六级仔细阅读真题精选（人工智能与教育）",
            "passage": "Far from rendering human teachers obsolete, artificial intelligence has the potential to liberate educators from tedious administrative grading so that they can focus on personalized mentorship. Nevertheless, experts caution that an over-reliance on automated feedback may compromise students' ability to engage in independent critical thinking, especially when algorithms prioritize standardized answers over creative inquiry.",
            "q1": "1. According to the passage, how can artificial intelligence benefit educators?",
            "q1_options": [
                "A) By completely replacing traditional classroom instruction.",
                "B) By freeing them from routine grading to guide students individually.",
                "C) By designing standardized exams that are easier to score.",
                "D) By eliminating the need for personalized mentorship."
            ],
            "q2": "2. What is the experts' concern regarding automated feedback?",
            "q2_options": [
                "A) It is too expensive for most public schools to implement.",
                "B) It may undermine students' capacity for independent critical thought.",
                "C) It fails to provide accurate grades for administrative tasks.",
                "D) It encourages students to challenge standardized answers."
            ],
            "analysis": "<b>【第1题答案】B</b>：定位首句 <code>liberate educators from tedious administrative grading so that they can focus on personalized mentorship</code>。B选项中的 <code>freeing them from</code> 同义替换 <code>liberate... from</code>，<code>guide students individually</code> 同义替换 <code>personalized mentorship</code>。<br><br><b>【第2题答案】B</b>：定位第二句转折词 <code>Nevertheless</code> 后：<code>compromise students' ability to engage in independent critical thinking</code>。这里考到了高频熟词僻义 <b>compromise（损害）</b>，对应B选项的 <b>undermine（削弱/损害）</b>。<br><br><b>【全文译文】</b>人工智能非但不会让人类教师变得多余，反而有潜力将教育工作者从繁琐的批改作业中解放出来，使他们能够专注于个性化指导。然而，专家警告称，过度依赖自动化反馈可能会损害学生进行独立批判性思考的能力，尤其是当算法优先考虑标准化答案而非创造性探究时。"
        },
        "translation": {
            "source": "六级翻译真题（中国古典园林）",
            "cn": "苏州园林以其精巧的设计闻名于世，完美体现了中国传统文化中“天人合一”的哲学理念。",
            "tips": "💡 <b>阅卷采分点：</b>① 以……闻名：<code>be renowned for</code>；② 精巧的设计：<code>exquisite design</code>；③ 用非谓语动词 <code>perfectly embodying</code> 连接后半句；④ 天人合一：<code>harmony between man and nature</code>。",
            "en": "Suzhou gardens are renowned worldwide for their exquisite design, perfectly embodying the philosophical concept of \"harmony between man and nature\" in traditional Chinese culture."
        }
    }

def render_html(data, is_weekend, days_left, today_str):
    mode_tag = "☕ 周末5分钟减负卷" if is_weekend else "📘 工作日真题随身卷"
    header_bg = "linear-gradient(135deg, #38a169, #276749)" if is_weekend else "linear-gradient(135deg, #2b6cb0, #1a365d)"

    # 1. 组装词汇 HTML（改为页内直接播放的 <audio> 控件，绝不跳转新网页！）
    words_list = []
    for w in data.get("words", []):
        raw_word_str = w.get("word", "")
        pure_word = raw_word_str.split("/")[0].strip()
        word_tts_url = f"https://dict.youdao.com/dictvoice?type=2&audio={urllib.parse.quote(pure_word)}"
        words_list.append(
            f'<div style="margin-bottom:12px; padding-bottom:10px; border-bottom:1px dashed #e2e8f0;">'
            f'<div style="margin-bottom:4px;"><b style="color:#2b6cb0; font-size:1.05em;">• {raw_word_str}</b></div>'
            f'<audio controls preload="none" style="width:100%; max-width:260px; height:30px; margin:2px 0 4px 0;" src="{word_tts_url}"></audio><br>'
            f'<span style="color:#c53030; font-weight:bold; font-size:0.92em;">{w.get("meaning", "")}</span><br>'
            f'<span style="color:#4a5568; font-size:0.88em;">👉 {w.get("collocation", "")}</span></div>'
        )
    words_html = "".join(words_list)

    # 2. 组装听力 HTML（使用专门支持长句子的【有道句子TTS】+【搜狗句子TTS】双引擎页内播放条！）
    listen = data.get("listening") or {}
    script_text = clean_for_tts(listen.get("script", ""))
    full_encoded = urllib.parse.quote(script_text)

    # 专门支持整段长句朗读的两个国内大厂 HTTPS 语音接口
    youdao_sent_url = f"https://tts.youdao.com/fanyivoice?word={full_encoded}&le=en&keyfrom=speaker-target"
    sogou_sent_url = f"https://fanyi.sogou.com/reventondc/synthesis?text={full_encoded}&speed=1&lang=en&from=translateweb&speaker=6"

    # 同时生成分句精听播放条（折叠起来，方便单句重听）
    sentences = split_sentences(script_text)
    sent_bars_html = ""
    for idx, sent in enumerate(sentences, 1):
        s_enc = urllib.parse.quote(sent)
        s_url = f"https://tts.youdao.com/fanyivoice?word={s_enc}&le=en&keyfrom=speaker-target"
        sent_bars_html += f"""
        <div style="margin-top:6px;">
            <span style="font-size:0.82em; color:#4a5568;">第 {idx} 句：</span>
            <audio controls preload="none" style="width:100%; height:30px;" src="{s_url}"></audio>
        </div>
        """

    listen_opts = "<br>".join(listen.get("options", []))
    listening_html = f"""
    <h3 style="color:#2b6cb0; border-left:4px solid #2b6cb0; padding-left:8px; margin:18px 0 8px 0;">🎧 一、真题听力盲听实战（页内直接播放）</h3>
    <div style="background:#f0f9ff; padding:12px; border-radius:8px; border:1px solid #bee3f8;">
        <div style="background:#ffffff; padding:10px; border-radius:6px; border:1px solid #bee3f8; margin-bottom:10px;">
            <p style="margin:0 0 4px 0; font-size:0.86em; font-weight:bold; color:#2b6cb0;">🔊 音源一（有道美音·整段连播，点 ▶ 直接听）：</p>
            <audio controls preload="none" style="width:100%; height:36px; margin-bottom:8px;" src="{youdao_sent_url}"></audio>
            <p style="margin:0 0 4px 0; font-size:0.84em; color:#4a5568;">🔊 音源二（搜狗外教·备用整段连播）：</p>
            <audio controls preload="none" style="width:100%; height:34px;" src="{sogou_sent_url}"></audio>
            <details style="margin-top:8px; cursor:pointer;">
                <summary style="font-size:0.84em; color:#3182ce;">👉 某一句没听清？点击展开【逐句单独播放条】</summary>
                {sent_bars_html}
            </details>
        </div>
        <p style="margin:10px 0 6px 0; font-weight:bold; color:#1a202c;">❓ {listen.get("question", "")}</p>
        <p style="margin:6px 0 12px 0; font-size:0.95em; line-height:1.7;">{listen_opts}</p>
        <details style="cursor:pointer; background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #cbd5e0;">
            <summary style="color:#2b6cb0; font-weight:bold;">👉 选好答案后，点击展开【听力原文 & 答案精析】</summary>
            <p style="margin:8px 0; font-size:0.92em; color:#2d3748;"><b>🎙️ 听力原文：</b>{script_text}</p>
            <p style="margin:6px 0 0 0; font-size:0.92em; color:#2f855a;">{listen.get("analysis", "")}</p>
        </details>
    </div>
    """

    # 3. 组装阅读 HTML
    reading_html = ""
    read = data.get("reading")
    if read and isinstance(read, dict):
        q1_opts = "<br>".join(read.get("q1_options", []))
        q2_opts = "<br>".join(read.get("q2_options", []))
        reading_html = f"""
        <h3 style="color:#2b6cb0; border-left:4px solid #2b6cb0; padding-left:8px; margin:18px 0 8px 0;">📖 二、真题仔细阅读实战（含同义替换定位）</h3>
        <div style="background:#faf5ff; padding:12px; border-radius:8px; border:1px solid #e9d8fd;">
            <p style="margin:0 0 6px 0; font-size:0.85em; color:#6b46c1; font-weight:bold;">📌 {read.get("source", "六级仔细阅读真题")}</p>
            <div style="background:#ffffff; padding:10px; border-radius:6px; border:1px solid #e2e8f0; margin-bottom:12px; font-size:0.96em; line-height:1.7; color:#1a202c;">
                {read.get("passage", "")}
            </div>
            <p style="margin:6px 0; font-weight:bold; color:#1a202c;">{read.get("q1", "")}</p>
            <p style="margin:4px 0 12px 0; font-size:0.93em; line-height:1.65;">{q1_opts}</p>
            <p style="margin:6px 0; font-weight:bold; color:#1a202c;">{read.get("q2", "")}</p>
            <p style="margin:4px 0 12px 0; font-size:0.93em; line-height:1.65;">{q2_opts}</p>
            <details style="cursor:pointer; background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #d6bcfa;">
                <summary style="color:#6b46c1; font-weight:bold;">👉 做完后，点击展开【答案、同义替换定位 & 全文译文】</summary>
                <div style="margin-top:8px; font-size:0.92em; color:#2d3748; line-height:1.65;">{read.get("analysis", "")}</div>
            </details>
        </div>
        """

    # 4. 组装翻译 HTML
    trans = data.get("translation") or {}
    sec_num = "二" if is_weekend else "三"
    word_num = "三" if is_weekend else "四"
    trans_html = f"""
    <h3 style="color:#2b6cb0; border-left:4px solid #2b6cb0; padding-left:8px; margin:18px 0 8px 0;">✍️ {sec_num}、历年翻译真题实战</h3>
    <div style="background:#fffaf0; padding:12px; border-radius:8px; border:1px solid #feebc8;">
        <p style="margin:0 0 6px 0; font-size:0.85em; color:#c05621;">📝 {trans.get("source", "六级翻译真题")}</p>
        <p style="margin:0 0 8px 0; font-weight:bold; color:#1a202c;">【真题原句】{trans.get("cn", "")}</p>
        <p style="margin:0 0 10px 0; font-size:0.9em; color:#7b341e; background:#feebc8; padding:6px 10px; border-radius:4px;">{trans.get("tips", "")}</p>
        <details style="cursor:pointer; background:#ffffff; padding:8px 10px; border-radius:6px; border:1px solid #fbd38d;">
            <summary style="color:#dd6b20; font-weight:bold;">👉 自己想完后，点击展开【高分参考译文】</summary>
            <p style="margin:8px 0 0 0; color:#2f855a; font-weight:bold;">{trans.get("en", "")}</p>
        </details>
    </div>
    """

    html = f"""
    <meta name="referrer" content="no-referrer">
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; line-height:1.6; color:#2d3748; max-width:650px;">
        <div style="background:{header_bg}; color:white; padding:14px 16px; border-radius:8px; margin-bottom:14px;">
            <h2 style="margin:0; font-size:1.18em;">🎯 {mode_tag} | 距六级仅剩 <span style="color:#fbd38d; font-size:1.25em;">{days_left}</span> 天</h2>
            <p style="margin:4px 0 0 0; font-size:0.85em; opacity:0.92;">不用到处找题！直接在当前页面完成今日【听+读+译+词】真题训练</p>
        </div>

        {listening_html}
        {reading_html}
        {trans_html}

        <h3 style="color:#2b6cb0; border-left:4px solid #2b6cb0; padding-left:8px; margin:18px 0 8px 0;">🔑 {word_num}、今日配套真题高频词 & 熟词僻义</h3>
        <div style="background:#f7fafc; padding:12px; border-radius:8px; border:1px solid #e2e8f0;">
            {words_html}
        </div>
    </div>
    """
    title = f"{mode_tag} | 六级倒计时 {days_left} 天 ({today_str[5:]})"
    return title, html

def build_daily_message():
    tz_bj = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_bj).date()
    days_left = (EXAM_DATE - today).days

    if days_left < 0:
        print("🎉 2026年12月六级考试已结束，自动停止推送！")
        return None, None

    if days_left == 0:
        title = "🔥 今天六级开考！考前终极抢分锦囊 & 必过祝福"
        html = """
        <div style="font-family:sans-serif; line-height:1.6; padding:15px; background:#fffaf0; border:2px solid #dd6b20; border-radius:8px;">
            <h2 style="color:#c05621; margin-top:0;">🎉 终于等到今天！祝你下午六级考的全会、蒙的全对！</h2>
            <p><b>⏰ 下午入场前最后叮嘱：</b></p>
            <ul>
                <li>检查证件：<b>准考证、身份证、学生证、调频耳机（及备用电池）、2B铅笔、黑色签字笔</b>。</li>
                <li><b>写作救急句：</b><code>It is universally acknowledged that...</code> / <code>Only by taking joint efforts can we...</code></li>
                <li><b>听力口诀：</b>视听一致抓主干，听到 <code>but / however / actually / in fact</code> 立刻竖起耳朵，答案就在后面！</li>
            </ul>
        </div>
        """
        return title, html

    weekday_idx = today.weekday()
    is_weekend = weekday_idx in (5, 6)
    day_idx = today.timetuple().tm_yday
    today_str = today.strftime("%Y-%m-%d")

    data = call_gemini_ai(is_weekend, days_left, today_str)
    if not data:
        print("使用内置全套真题库兜底")
        data = get_fallback_data(is_weekend, day_idx)

    return render_html(data, is_weekend, days_left, today_str)

def push_wechat(title, html):
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        return
    res = requests.post("http://www.pushplus.plus/send", json={
        "token": token, "title": title, "content": html, "template": "html"
    }, timeout=15)
    print("微信推送结果:", res.text)

def push_email(title, html):
    sender = (os.environ.get("EMAIL_SENDER") or "").strip()
    password = (os.environ.get("EMAIL_PASSWORD") or "").strip().replace(" ", "")
    receiver = (os.environ.get("EMAIL_RECEIVER") or sender).strip()
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    if not (sender and password):
        return
    try:
        msg = MIMEText(html, "html", "utf-8")
        msg["From"] = sender
        msg["To"] = receiver
        msg["Subject"] = Header(title, "utf-8")

        server = smtplib.SMTP_SSL(smtp_server, 465, timeout=20)
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
        try:
            server.quit()
        except Exception:
            pass
        print("🎉 邮箱推送成功！")
    except Exception as e:
        print(f"❌ 邮箱推送失败，具体原因: {e}")

if __name__ == "__main__":
    title, html = build_daily_message()
    if title and html:
        push_wechat(title, html)
        push_email(title, html)
