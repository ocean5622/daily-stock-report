import os
import csv
import requests
import yfinance as yf
from datetime import datetime
import time
import random

# --- 配置 ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# --- 关键修复：设置全局 User-Agent，伪装成浏览器 ---
yf.enable_debug_mode() # 可选：开启调试看详细日志
# 这里的核心是欺骗 Yahoo Finance，让它以为我们是浏览器而不是机器人
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
})
yf.set_ticker_session(session)

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

# --- 2. 获取行情数据 (带重试机制) ---
market_data = []
print("正在获取行情数据...")

for stock in portfolio:
    ticker = stock['ticker']
    success = False
    
    # 最多重试 3 次
    for attempt in range(3):
        try:
            print(f"尝试获取 {ticker} (第 {attempt+1} 次)...")
            # 创建 Ticker 对象
            tk = yf.Ticker(ticker)
            # 获取历史数据
            hist = tk.history(period="5d")
            
            if not hist.empty and len(hist) >= 2:
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
                print(f"✅ {ticker} 获取成功: ${close_curr}")
                success = True
                break # 成功后跳出重试循环
            else:
                print(f"⚠️ {ticker} 数据不足，跳过。")
                break # 数据不足无需重试
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ {ticker} 失败: {error_msg}")
            # 如果是网络限流 (-2 或 429)，等待随机时间后重试
            if "-2" in error_msg or "429" in error_msg or "Too Many Requests" in error_msg:
                wait_time = random.uniform(2, 5) # 随机等待 2-5 秒
                print(f"   -> 疑似被限流，等待 {wait_time:.1f} 秒后重试...")
                time.sleep(wait_time)
            else:
                break # 其他错误直接放弃

    if not success and len(market_data) == 0:
        # 如果连一个都没获取到，稍微多等一会再试下一个，防止连续被封
        time.sleep(3)

# --- 检查结果 ---
if not market_data:
    ai_report = "⚠️ **数据获取失败**\n\nGitHub 服务器无法连接 Yahoo Finance，可能是网络波动或被临时限流。\n\n建议：\n1. 稍后手动重新运行 Workflow。\n2. 检查股票代码是否正确。\n\n原始日志显示所有请求均返回 -2。"
    # 即使没数据，也尝试发送这个错误通知，让你知道出事了
else:
    # --- 3. 构建提示词 ---
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
    1. **总览**：一句话总结昨夜整体市场表现。
    2. **个股点评**：对每只股票简要分析涨跌原因。
    3. **操作建议**：给出简短建议（持有/减仓/关注）。
    4. **风格**：专业、简洁，直接说结论。
    5. **格式**：使用 Markdown 格式。
    """

    # --- 4. 调用 DeepSeek API ---
    print("正在请求 DeepSeek AI...")
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
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
        ai_report = f"⚠️ AI 分析失败：{str(e)}\n\n原始数据:\n{data_text}"

# --- 5. 推送到企业微信 ---
print("正在发送消息...")
if len(ai_report) > 3800:
    ai_report = ai_report[:3800] + "\n...(内容过长)"

wechat_payload = {
    "msgtype": "markdown",
    "markdown": {
        "content": f"### 🇺🇸 美股晨报\n📅 日期：{datetime.now().strftime('%Y-%m-%d')}\n\n{ai_report}"
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
