import os
import csv
import requests
import yfinance as yf
from datetime import datetime

# --- 配置 ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# --- 1. 读取持仓 ---
portfolio = []
try:
    with open('portfolio.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            portfolio.append(row)
except Exception as e:
    print(f"读取 CSV 失败: {e}")
    exit(1)

# --- 2. 获取行情数据 (Yahoo Finance) ---
market_data = []
print("正在获取行情数据...")
for stock in portfolio:
    ticker = stock['ticker']
    try:
        # 获取最近 5 天数据以防周末/节假日
        hist = yf.Ticker(ticker).history(period="5d")
        if len(hist) >= 2:
            close_prev = hist['Close'][-2]
            close_curr = hist['Close'][-1]
            change_pct = ((close_curr - close_prev) / close_prev) * 100
            market_value = close_curr * int(stock['qty'])
            
            market_data.append({
                "ticker": ticker,
                "name": stock['name'],
                "qty": stock['qty'],
                "price": round(float(close_curr), 2),
                "change": round(float(change_pct), 2),
                "value": round(float(market_value), 2)
            })
    except Exception as e:
        print(f"获取 {ticker} 数据失败: {e}")

if not market_data:
    print("未获取到任何有效数据，停止运行。")
    exit(0)

# --- 3. 构建提示词 (Prompt) ---
data_text = "\n".join([
    f"- {d['name']} ({d['ticker']}): 持有 {d['qty']} 股, 现价 ${d['price']}, 涨跌 {d['change']:+.2f}%, 市值 ${d['value']}"
    for d in market_data
])

total_value = sum(d['value'] for d in market_data)
today_str = datetime.now().strftime("%Y年%m月%d日")

prompt = f"""
你是一位专业的美股投资顾问。请根据以下数据，为我生成一份【{today_str}】的美股晨报。

我的持仓数据：
{data_text}
总市值约为：${total_value:.2f}

要求：
1. **总览**：一句话总结昨夜整体市场表现及我的账户盈亏概况。
2. **个股点评**：对每只股票，结合昨夜美股大盘走势或行业消息（利用你的知识库），简要分析涨跌原因。
3. **操作建议**：针对每只股票给出简短建议（如：继续持有、关注支撑位、止盈等）。
4. **风格**：专业、客观、简洁，直接说结论，不要废话。
5. **格式**：使用清晰的 Markdown 格式，方便手机阅读。
"""

# --- 4. 调用 DeepSeek API ---
print("正在请求 DeepSeek AI 分析...")
headers = {
    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    "Content-Type": "application/json"
}
payload = {
    "model": "deepseek-chat",  # 使用 deepseek-chat 模型
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.7,
    "max_tokens": 1000
}

ai_report = ""
try:
    response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    ai_report = response.json()['choices'][0]['message']['content']
except Exception as e:
    ai_report = f"⚠️ AI 分析服务暂时不可用：{str(e)}\n\n原始数据如下:\n{data_text}"

# --- 5. 推送到企业微信 ---
print("正在发送消息到企业微信...")
# 企业微信 Markdown 限制 4096 字节，若过长需截断
if len(ai_report) > 3800:
    ai_report = ai_report[:3800] + "\n...(内容过长已截断)"

wechat_payload = {
    "msgtype": "markdown",
    "markdown": {
        "content": f"### 🇺🇸 美股晨报 (DeepSeek 版)\n📅 日期：{today_str}\n\n{ai_report}"
    }
}

try:
    resp = requests.post(WECHAT_WEBHOOK, json=wechat_payload, timeout=10)
    if resp.status_code == 200:
        print("✅ 发送成功！")
    else:
        print(f"❌ 发送失败: {resp.text}")
except Exception as e:
    print(f"❌ 网络错误: {e}")
