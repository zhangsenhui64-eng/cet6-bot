import os
import re
import time
import json
import base64
import asyncio
import smtplib
import datetime
import urllib.parse
import requests
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio
from email.mime.multipart import MIMEMultipart
from email.header import Header

# 2026年下半年六级考试日期：2026年12月12日（考完次日自动停止推送）
EXAM_DATE = datetime.date(2026, 12, 12)

def clean_for_tts(text):
    text = text.replace("\n", " ").replace('"', "").replace("“", "").replace("”", "").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()

def generate_listening_mp3(script_text, out_path="today_listening.mp3"):
    """在 GitHub Actions 云端直接合成真实 MP3 听力音频（微软 Edge 神经语音优先 + Google 语音兜底）"""
    text = clean_for_tts(script_text)
    if not text:
        return False

    # 1. 优先使用微软 Edge-TTS（en-US-JennyNeural，六级考场标准美音女声，语速微调至 -5%）
    try:
        import edge_tts
        async def _run():
            communicate = edge_tts.Communicate(text, "en-US-JennyNeural", rate="-5%")
            await communicate.save(out_path)
        asyncio.run(_run())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 2000:
            print(f"✅ edge-tts 合成真实 MP3 成功！大小: {os.path.getsize(out_path)} 字节")
            return True
    except Exception as e:
        print(f"⚠️ edge-tts 合成提示: {e}")

    # 2. 备用使用 gTTS（Google TTS，GitHub 海外服务器 100% 畅通）
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en", tld="us")
        tts.save(out_path)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 2000:
            print(f"✅ gTTS 合成真实 MP3 成功！大小: {os.path.getsize(out_path)} 字节")
            return True
    except Exception as e:
        print(f"❌ gTTS 合成异常: {e}")

    return False

def upload_mp3_and_verify(mp3_path, repo_file_path):
    """把生成的 MP3 上传至你的 GitHub 仓库，并实测国内 CDN 链接是否真正返回 MP3"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if not (token and repo and os.path.exists(mp3_path)):
        return None

    with open(mp3_path, "rb") as f:
        b64_content = base64.b64encode(f.read()).decode("utf-8")

    api_url = f"https://api.github.com/repos/{repo}/contents/{repo_file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    sha = None
    try:
        r_get = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=15)
        if r_get.status_code == 200:
            sha = r_get.json().get("sha")
    except Exception:
        pass

    payload = {
        "message": f"Add CET-6 listening audio {repo_file_path}",
        "content": b64_content,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    r_put = requests.put(api_url, headers=headers, json=payload, timeout=30)
    if r_put.status_code not in (200, 201):
        print(f"❌ 上传 MP3 至仓库失败 ({r_put.status_code}): {r_put.text}")
        return None

    print(f"✅ MP3 已成功存入仓库: {repo_file_path}")
    fastly_url = f"https://fastly.jsdelivr.net/gh/{repo}@{branch}/{repo_file_path}"
    gcore_url = f"https://gcore.jsdelivr.net/gh/{repo}@{branch}/{repo_file_path}"
    cdn_url = f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{repo_file_path}"

    # 等待 2 秒让节点同步，并主动测试音频地址是否真正可下载播放
    time.sleep(2)
    best_url = fastly_url
    for u in (fastly_url, gcore_url, cdn_url):
        try:
            chk = requests.get(u, timeout=15)
            ctype = chk.headers.get("Content-Type", "")
            print(f"🔎 实测音频地址 {u} -> HTTP {chk.status_code}, 类型: {ctype}, 大小: {len(chk.content)} 字节")
            if chk.status_code == 200 and len(chk.content) > 2000:
                best_url = u
                break
        except Exception as e:
            print(f"检测 {u} 异常: {e}")

    return {"primary": best_url, "fastly": fastly_url, "gcore": gcore_url}

def call_gemini_ai(is_weekend, days_left, today_str):
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
        请严格按以下 JSON 格式返回今日轻量真题保温内容（只输出纯 JSON）：
        {{
          "words": [
            {{"word": "单词 /音标/", "meaning": "【真题熟词僻义】常考词义", "collocation": "真题搭配与同义替换"}},
            {{"word": "单词 /音标/", "meaning": "【真题高频】常考词义", "collocation": "真题搭配与同义替换"}}
          ],
          "listening": {{
            "script": "一段45-60词的六级真题听力短文或对话节选（纯英文，包含 but 或 however 等转折考点，无换行）",
            "question": "针对上述听力内容的1道六级标准英文设问？",
            "options": ["A) 选项A", "B) 选项B", "C) 选项C", "D) 选项D"],
            "analysis": "正确答案及解析（指出转折信号词及中文译文）"
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
            "script": "一段60-80词的六级真题听力讲座(Section C)或短文核心节选（纯英文，必须包含 however, actually, in fact 等转折出题信号词，单段落无换行）",
            "question": "What does the speaker mainly imply / talk about ...?",
            "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "analysis": "【正确答案】及【听音关键点】：指出哪个信号词对应正确选项，并附听力原文中文译文。"
          }},
          "reading": {{
            "source": "六级仔细阅读真题精选（标明题材）",
            "passage": "一段120-150词的六级仔细阅读真题核心段落（包含长难句与同义替换考点）",
            "q1": "1. 第1道仔细阅读真题英文题干",
            "q1_options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "q2": "2. 第2道仔细阅读真题英文题干",
            "q2_options": ["A) ...", "B) ...", "C) ...", "D) ..."],
            "analysis": "【答案与同义替换精析】：分别解析第1、2题的正确选项如何同义改写原文，并附全文译文。"
          }},
          "translation": {{
            "source": "历年六级翻译真题（标明主题）",
            "cn": "1句经典的六级真题翻译中文原句（约25-40字）",
            "tips": "💡 阅卷采分点：列出2-3个核心词组和句型结构",
            "en": "高分地道英文参考译文"
          }}
        }}
        """

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}
        }
        try:
            res = requests.post(url, json=payload, timeout=40)
            if res.status_code == 200:
                print(f"✅ 成功调用 Google AI 模型: {model}！")
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            else:
                print(f"⏳ 模型 {model} 状态码 {res.status_code}，切换下一个模型...")
        except Exception as e:
            print(f"⏳ 模型 {model} 异常，切换下一个模型: {e}")
    return None

def get_fallback_data(is_weekend):
    return {
        "words": [
            {"word": "compromise /ˈkɒmprəmaɪz/", "meaning": "【真题熟词僻义】v. 损害，危及；妥协", "collocation": "compromise safety（损害安全，替换 jeopardize / undermine）"},
            {"word": "scrutiny /ˈskruːtəni/", "meaning": "【真题高频】n. 仔细审查，严密监督", "collocation": "come under close scrutiny（受到严格审查，替换 inspection）"},
            {"word": "alleviate /əˈliːvieɪt/", "meaning": "【真题核心】v. 减轻，缓和（痛苦/贫困）", "collocation": "alleviate poverty（缓解贫困，反义词 aggravate 加剧）"}
        ],
        "listening": {
            "script": "Many people assume that working longer hours leads to higher productivity. However, recent studies across European countries reveal the exact opposite. Once employees exceed forty-five hours a week, their efficiency drops sharply due to mental fatigue, and they are far more likely to make costly mistakes.",
            "question": "What do recent studies reveal about working longer hours?",
            "options": [
                "A) It significantly boosts a company's overall profit.",
                "B) It actually reduces efficiency and increases errors.",
                "C) It is widely welcomed by European employers.",
                "D) It helps employees develop stronger mental endurance."
            ],
            "analysis": "<b>【正确答案】B</b><br><b>【听音关键点】</b>注意转折词 <code>However</code> 后：<code>efficiency drops sharply due to mental fatigue... make costly mistakes</code>。<br><b>【原文译文】</b>许多人认为延长工作时间会提高生产力。然而，欧洲多国的研究揭示了完全相反的结果。员工每周工作超45小时后，效率会因精神疲劳急剧下降，且更容易犯错。"
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
            "analysis": "<b>【第1题】B</b>（<code>freeing them from</code> 同义替换 <code>liberate... from</code>）；<b>【第2题】B</b>（<code>undermine</code> 同义替换熟词僻义 <code>compromise</code>）。<br><b>【全文译文】</b>AI非但不会淘汰教师，反而能把他们从繁琐批改中解放出来专注个性化指导。但专家警告，过度依赖自动化反馈可能损害学生的独立批判性思维能力。"
        },
        "translation": {
            "source": "六级翻译真题（中国古典园林）",
            "cn": "苏州园林以其精巧的设计闻名于世，完美体现了中国传统文化中“天人合一”的哲学理念。",
            "tips": "💡 <b>采分点：</b><code>be renowned for</code>（以…闻名）；<code>exquisite design</code>；非谓语 <code>perfectly embodying</code>；<code>harmony between man and nature</code>。",
            "en": "Suzhou gardens are renowned worldwide for their exquisite design, perfectly embodying the philosophical concept of \"harmony between man and nature\" in traditional Chinese culture."
        }
    }

def render_html(data, is_weekend, days_left, today_str, audio_urls):
    mode_tag = "☕ 周末5分钟减负卷" if is_weekend else "📘 工作日真题随身卷"
    header_bg = "#276749" if is_weekend else "#2b6cb0"

    # 词汇 HTML（单字用有道单词页内播放条）
    words_list = []
    for w in data.get("words", []):
        raw_word_str = w.get("word", "")
        pure_word = raw_word_str.split("/")[0].strip()
        word_tts_url = f"https://dict.youdao.com/dictvoice?type=2&audio={urllib.parse.quote(pure_word)}"
        words_list.append(
            f'<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px dashed #e2e8f0;">'
            f'<b style="color:#2b6cb0;">• {raw_word_str}</b><br>'
            f'<audio controls preload="none" style="width:100%;max-width:250px;height:28px;margin:3px 0;" src="{word_tts_url}"></audio><br>'
            f'<span style="color:#c53030;font-weight:bold;font-size:0.9em;">{w.get("meaning", "")}</span><br>'
            f'<span style="color:#4a5568;font-size:0.86em;">👉 {w.get("collocation", "")}</span></div>'
        )
    words_html = "".join(words_list)

    # 听力 HTML（挂载自建真实 MP3 文件，并附 QQ邮箱附件提示）
    listen = data.get("listening") or {}
    script_text = clean_for_tts(listen.get("script", ""))
    listen_opts = "<br>".join(listen.get("options", []))

    if audio_urls:
        p_url = audio_urls["primary"]
        backup_url = audio_urls["gcore"] if p_url != audio_urls["gcore"] else audio_urls["fastly"]
        player_block = f"""
        <p style="margin:0 0 6px 0;font-size:0.86em;color:#2c5282;">👇 <b>点击下方播放按钮盲听（真人神经语音 MP3，QQ邮箱用户可直接点邮件底部的 MP3 附件播放）：</b></p>
        <audio controls preload="metadata" style="width:100%;height:38px;margin-bottom:6px;" src="{p_url}"></audio>
        <div style="font-size:0.8em;color:#4a5568;margin-bottom:8px;">
            备用通道：<a href="{p_url}" style="color:#2b6cb0;">点此打开音频文件</a> |
            <a href="{backup_url}" style="color:#2b6cb0;">备用镜像通道</a>
        </div>
        """
    else:
        player_block = '<p style="color:#c53030;font-size:0.86em;">（今日在线语音通道未就绪，请直接点击邮件附件 MP3 或展开原文跟读）</p>'

    listening_html = f"""
    <h3 style="color:#2b6cb0;border-left:4px solid #2b6cb0;padding-left:8px;margin:14px 0 8px 0;">🎧 一、真题听力盲听实战</h3>
    <div style="background:#f0f9ff;padding:10px;border-radius:6px;border:1px solid #bee3f8;">
        {player_block}
        <p style="margin:6px 0;font-weight:bold;">❓ {listen.get("question", "")}</p>
        <p style="margin:4px 0 10px 0;font-size:0.93em;">{listen_opts}</p>
        <details style="background:#fff;padding:8px;border-radius:4px;border:1px solid #cbd5e0;">
            <summary style="color:#2b6cb0;font-weight:bold;">👉 选好后点击展开【听力原文 & 解析】</summary>
            <p style="margin:6px 0;font-size:0.9em;"><b>原文：</b>{script_text}</p>
            <p style="margin:4px 0 0 0;font-size:0.9em;color:#2f855a;">{listen.get("analysis", "")}</p>
        </details>
    </div>
    """

    reading_html = ""
    read = data.get("reading")
    if read and isinstance(read, dict):
        q1_opts = "<br>".join(read.get("q1_options", []))
        q2_opts = "<br>".join(read.get("q2_options", []))
        reading_html = f"""
        <h3 style="color:#2b6cb0;border-left:4px solid #2b6cb0;padding-left:8px;margin:14px 0 8px 0;">📖 二、真题仔细阅读实战</h3>
        <div style="background:#faf5ff;padding:10px;border-radius:6px;border:1px solid #e9d8fd;">
            <p style="margin:0 0 6px 0;font-size:0.84em;color:#6b46c1;font-weight:bold;">📌 {read.get("source", "六级阅读真题")}</p>
            <div style="background:#fff;padding:8px;border-radius:4px;border:1px solid #e2e8f0;margin-bottom:10px;font-size:0.94em;">{read.get("passage", "")}</div>
            <p style="margin:4px 0;font-weight:bold;">{read.get("q1", "")}</p>
            <p style="margin:2px 0 10px 0;font-size:0.92em;">{q1_opts}</p>
            <p style="margin:4px 0;font-weight:bold;">{read.get("q2", "")}</p>
            <p style="margin:2px 0 10px 0;font-size:0.92em;">{q2_opts}</p>
            <details style="background:#fff;padding:8px;border-radius:4px;border:1px solid #d6bcfa;">
                <summary style="color:#6b46c1;font-weight:bold;">👉 做完点击展开【答案与同义替换精析】</summary>
                <div style="margin-top:6px;font-size:0.9em;">{read.get("analysis", "")}</div>
            </details>
        </div>
        """

    trans = data.get("translation") or {}
    sec_num = "二" if is_weekend else "三"
    word_num = "三" if is_weekend else "四"
    trans_html = f"""
    <h3 style="color:#2b6cb0;border-left:4px solid #2b6cb0;padding-left:8px;margin:14px 0 8px 0;">✍️ {sec_num}、历年翻译真题实战</h3>
    <div style="background:#fffaf0;padding:10px;border-radius:6px;border:1px solid #feebc8;">
        <p style="margin:0 0 4px 0;font-size:0.84em;color:#c05621;">📝 {trans.get("source", "六级翻译真题")}</p>
        <p style="margin:0 0 6px 0;font-weight:bold;">【真题原句】{trans.get("cn", "")}</p>
        <p style="margin:0 0 8px 0;font-size:0.88em;color:#7b341e;background:#feebc8;padding:6px;border-radius:4px;">{trans.get("tips", "")}</p>
        <details style="background:#fff;padding:8px;border-radius:4px;border:1px solid #fbd38d;">
            <summary style="color:#dd6b20;font-weight:bold;">👉 点击展开【高分参考译文】</summary>
            <p style="margin:6px 0 0 0;color:#2f855a;font-weight:bold;">{trans.get("en", "")}</p>
        </details>
    </div>
    """

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;line-height:1.55;color:#2d3748;max-width:650px;">
        <div style="background:{header_bg};color:#fff;padding:12px 14px;border-radius:8px;margin-bottom:12px;">
            <h2 style="margin:0;font-size:1.15em;">🎯 {mode_tag} | 距六级仅剩 <span style="color:#fbd38d;">{days_left}</span> 天</h2>
            <p style="margin:3px 0 0 0;font-size:0.82em;opacity:0.9;">真实 MP3 真题语音 + 阅读 + 翻译 + 高频词每日直达</p>
        </div>
        {listening_html}
        {reading_html}
        {trans_html}
        <h3 style="color:#2b6cb0;border-left:4px solid #2b6cb0;padding-left:8px;margin:14px 0 8px 0;">🔑 {word_num}、今日配套真题高频词</h3>
        <div style="background:#f7fafc;padding:10px;border-radius:6px;border:1px solid #e2e8f0;">
            {words_html}
        </div>
    </div>
    """
    title = f"{mode_tag} | 六级倒计时 {days_left} 天 ({today_str[5:]})"
    return title, html

def build_daily_message():
    tz_bj = datetime.timezone(datetime.timedelta(hours=8))
    now_bj = datetime.datetime.now(tz_bj)
    today = now_bj.date()
    days_left = (EXAM_DATE - today).days

    if days_left < 0:
        print("🎉 2026年12月六级考试已结束，自动停止推送！")
        return None, None, None

    if days_left == 0:
        title = "🔥 今天六级开考！考前终极抢分锦囊"
        html = "<div style='padding:15px;background:#fffaf0;'><h2>🎉 祝你今天六级必过！</h2><p>带齐准考证、身份证、学生证、调频耳机及备用电池！</p></div>"
        return title, html, None

    is_weekend = today.weekday() in (5, 6)
    today_str = today.strftime("%Y-%m-%d")

    data = call_gemini_ai(is_weekend, days_left, today_str)
    if not data:
        print("使用内置全套真题库兜底")
        data = get_fallback_data(is_weekend)

    # 1. 云端合成真实 MP3 文件
    mp3_local = "today_listening.mp3"
    script_text = (data.get("listening") or {}).get("script", "")
    mp3_ok = generate_listening_mp3(script_text, mp3_local)

    # 2. 上传到仓库并实测音频链接可用性
    audio_urls = None
    if mp3_ok:
        stamp = now_bj.strftime("%Y%m%d_%H%M%S")
        audio_urls = upload_mp3_and_verify(mp3_local, f"audio/{stamp}.mp3")

    title, html = render_html(data, is_weekend, days_left, today_str, audio_urls)
    return title, html, (mp3_local if mp3_ok else None)

def push_wechat(title, html):
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        return
    print(f"PushPlus HTML 字符长度: {len(html)}")
    res = requests.post("http://www.pushplus.plus/send", json={
        "token": token, "title": title, "content": html, "template": "html"
    }, timeout=15)
    print("微信推送结果:", res.text)

def push_email(title, html, mp3_path=None):
    sender = (os.environ.get("EMAIL_SENDER") or "").strip()
    password = (os.environ.get("EMAIL_PASSWORD") or "").strip().replace(" ", "")
    receiver = (os.environ.get("EMAIL_RECEIVER") or sender).strip()
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    if not (sender and password):
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = receiver
        msg["Subject"] = Header(title, "utf-8")
        msg.attach(MIMEText(html, "html", "utf-8"))

        # 直接把真实听力 MP3 作为附件放进邮件，100% 原生可播！
        if mp3_path and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1000:
            with open(mp3_path, "rb") as f:
                audio_part = MIMEAudio(f.read(), _subtype="mpeg")
                audio_part.add_header("Content-Disposition", "attachment", filename="cet6_listening.mp3")
                msg.attach(audio_part)
            print("📎 已将真实 MP3 听力作为邮件附件打包！")

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
    title, html, mp3_path = build_daily_message()
    if title and html:
        push_wechat(title, html)
        push_email(title, html, mp3_path)
