import os
import smtplib
import datetime
import requests
from email.mime.text import MIMEText
from email.header import Header

# ================= 1. 基础配置 =================
# 2026年下半年六级笔试时间为 2026-12-12（若考2027年6月可改为 2027-06-12）
EXAM_DATE = datetime.date(2026, 12, 12)

# 每周固定复习计划表（可根据你的薄弱项修改）
WEEKLY_PLAN = {
    0: ["🎧 听力：精听 1 篇六级长对话 + 1 篇短文（盲听->对原文->跟读）", "📖 阅读：完成 2 篇仔细阅读（限时 18 分钟），整理生词"],
    1: ["✍️ 翻译：独立完成 1 篇六级真题段落翻译，对照参考译文复盘", "📖 阅读：完成 1 篇长篇阅读（段落匹配，限时 15 分钟）"],
    2: ["🎧 听力：精听 2 篇六级讲座/讲话（把握开头、转折和结尾信号词）", "📖 阅读：完成 1 篇选词填空 + 1 篇仔细阅读"],
    3: ["📝 写作：背诵 3 个高分句型，并限时 30 分钟写 1 篇六级真题作文", "📖 阅读：完成 2 篇仔细阅读，拆解文中的 2 个长难句"],
    4: ["🎧 听力：完整做 1 套真题听力（限时涂卡），重点复盘错题原文", "✍️ 翻译：积累 10 个中国传统文化/经济社科类高频表达"],
    5: ["🔥 周六模考：下午 15:00-17:25 严格掐表完成 1 整套六级真题！", "🧐 复盘：核对答案，算出预估分，标记所有蒙对和做错的题"],
    6: ["🔄 周日复盘：彻底吃透周六真题里的阅读错题和听力盲区", "📚 词汇大扫除：复习本周打卡过的所有六级核心词"]
}

# 内置六级高频词汇池（按天数自动轮换）
WORD_BANK = [
    ("deteriorate /dɪˈtɪəriəreɪt/", "v. 恶化，变坏", "The economic situation continued to deteriorate."),
    ("unprecedented /ʌnˈpresɪdentɪd/", "adj. 史无前例的，空前的", "Technology is advancing at an unprecedented rate."),
    ("indispensable /ˌɪndɪˈspensəbl/", "adj. 不可或缺的，必需的", "A good dictionary is indispensable for learning a foreign language."),
    ("vulnerable /ˈvʌlnərəbl/", "adj. 脆弱的，易受伤害的", "Children are the most vulnerable members of society."),
    ("compensate /ˈkɒmpenseɪt/", "v. 补偿，弥补（常搭配 for）", "Nothing can compensate for the loss of a loved one."),
    ("foster /ˈfɒstə(r)/", "v. 促进，培养，助长", "The workshop aims to foster creativity and innovation."),
    ("jeopardize /ˈdʒepədaɪz/", "v. 危及，损害", "He would never do anything to jeopardize his career."),
    ("scrutiny /ˈskruːtəni/", "n. 仔细检查，认真审视", "The government's record will be subjected to close scrutiny."),
    ("alleviate /əˈliːvieɪt/", "v. 减轻，缓和（痛苦、贫困等）", "Measures have been taken to alleviate poverty in rural areas."),
    ("paradigm /ˈpærədaɪm/", "n. 范式，典范，模式", "AI has brought a new paradigm to scientific research."),
    ("constrained /kənˈstreɪnd/", "adj. 受制约的，受限制的", "Economic growth was constrained by a lack of investment."),
    ("empirical /ɪmˈpɪrɪkl/", "adj. 实证的，以经验为依据的", "There is no empirical evidence to support his hypothesis."),
    ("intrinsic /ɪnˈtrɪnzɪk/", "adj. 固有的，内在的，本质的", "Critical thinking has intrinsic value in higher education."),
    ("proliferate /prəˈlɪfəreɪt/", "v. 激增，迅速繁殖/扩散", "Digital platforms have proliferated over the past decade."),
    ("ambiguity /ˌæmbɪˈɡjuːəti/", "n. 模棱两可，含糊不清", "Write clearly to avoid any ambiguity in your essay.")
]

# 内置六级汉译英每日一练（按天数轮换）
TRANS_BANK = [
    ("随着人们环保意识的不断提高，低碳生活已成为一种新时尚。", 
     "With the continuous improvement of people's awareness of environmental protection, low-carbon life has become a new fashion."),
    ("科技创新不仅推动了经济的可持续发展，也深刻改变了人们的日常生活。", 
     "Technological innovation has not only promoted sustainable economic development, but also profoundly changed people's daily lives."),
    ("中国传统文化博大精深，吸引着越来越多的外国年轻人前来探索。", 
     "Traditional Chinese culture is extensive and profound, attracting more and more young foreigners to explore it."),
    ("在信息爆炸的时代，具备独立思考和辨别真伪的能力显得尤为重要。", 
     "In an era of information explosion, having the ability to think independently and distinguish truth from falsehood is particularly important."),
    ("政府已经采取了一系列有效措施，以缩小城乡之间的教育差距。", 
     "The government has taken a series of effective measures to narrow the educational gap between urban and rural areas.")
]

def get_daily_quote():
    """获取金山词霸每日一句"""
    try:
        res = requests.get("https://open.iciba.com/dsapi/", timeout=10).json()
        return res.get("content", ""), res.get("note", "")
    except Exception:
        return "Persistence guarantees that results are inevitable.", "坚持保证结果是必然的。"

def build_content():
    # 获取北京时间 (UTC+8)
    tz_bj = datetime.timezone(datetime.timedelta(hours=8))
    today = datetime.datetime.now(tz_bj).date()
    days_left = (EXAM_DATE - today).days
    weekday_idx = today.weekday()
    day_of_year = today.timetuple().tm_yday

    # 抽取今日词汇（每天3个核心词精背）和今日翻译
    words_today = [WORD_BANK[(day_of_year * 3 + i) % len(WORD_BANK)] for i in range(3)]
    trans_q, trans_a = TRANS_BANK[day_of_year % len(TRANS_BANK)]
    quote_en, quote_cn = get_daily_quote()
    tasks = WEEKLY_PLAN[weekday_idx]

    countdown_str = f"距离六级考试还有 <b>{days_left}</b> 天" if days_left >= 0 else "六级持续进阶打卡中"
    title = f"📅 六级每日打卡 | 倒计时 {days_left} 天 ({today.strftime('%m-%d')})"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #2b6cb0; border-bottom: 2px solid #2b6cb0; padding-bottom: 8px;">
            🎯 {countdown_str}
        </h2>
        
        <h3 style="color: #2c5282;">✅ 今日必做任务清单</h3>
        <ul>
            {''.join(f'<li style="margin-bottom: 6px;"><b>{t}</b></li>' for t in tasks)}
            <li style="margin-bottom: 6px;"><b>🔤 背诵下方 3 个六级高频核心词 + 完成 1 句翻译</b></li>
        </ul>

        <h3 style="color: #2c5282;">📘 今日六级核心词</h3>
        <div style="background: #f7fafc; padding: 12px; border-left: 4px solid #4299e1; border-radius: 4px;">
            {''.join(f'<p style="margin: 6px 0;"><b>• {w[0]}</b>：{w[1]}<br><span style="color:#666; font-size:0.9em;">例：{w[2]}</span></p>' for w in words_today)}
        </div>

        <h3 style="color: #2c5282;">✍️ 每日汉译英一练（先自己翻，再看参考答案）</h3>
        <p style="background: #fffaf0; padding: 10px; border-left: 4px solid #ed8936;">
            <b>原句：</b>{trans_q}
        </p>
        <details style="margin-bottom: 15px; cursor: pointer;">
            <summary style="color: #dd6b20; font-weight: bold;">👉 点击展开参考译文</summary>
            <p style="color: #2f855a; background: #f0fff4; padding: 8px; border-radius: 4px;">{trans_a}</p>
        </details>

        <hr style="border: none; border-top: 1px dashed #cbd5e0; margin: 16px 0;">
        <p style="font-size: 0.9em; color: #718096;">
            💡 <b>每日一句：</b>{quote_en}<br>{quote_cn}<br><br>
            <i>做完今天的翻译或作文后，记得直接发给 AI 帮你批改打分哦！</i>
        </p>
    </div>
    """
    return title, html

def push_wechat(title, html):
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        return
    url = "http://www.pushplus.plus/send"
    data = {"token": token, "title": title, "content": html, "template": "html"}
    res = requests.post(url, json=data, timeout=15)
    print("微信推送结果:", res.text)

def push_email(title, html):
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    receiver = os.environ.get("EMAIL_RECEIVER") or sender
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.qq.com")
    if not (sender and password):
        return
    msg = MIMEText(html, "html", "utf-8")
    msg["From"] = Header(f"六级督学助手 <{sender}>", "utf-8")
    msg["To"] = Header(receiver, "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    with smtplib.SMTP_SSL(smtp_server, 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [receiver], msg.as_string())
    print("邮箱推送成功！")

if __name__ == "__main__":
    title, html = build_content()
    push_wechat(title, html)
    push_email(title, html)
