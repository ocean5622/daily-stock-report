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

# --- 关键修复：全局设置 User-Agent ---
# 新版 yfinance 不再支持 set_ticker_session，我们直接修改 requests 的默认头
# 这样 yfinance 内部发起的请求也会带上这个头
import urllib3
urllib3.addinfourl = None # 防止某些版本冲突

# 定义一个自定义的 Session 类来注入 Header
class CustomSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })

# 挂载自定义 Session 到 yfinance (如果 yfinance 版本支持)
# 如果不支持，我们在每次请求时手动处理（见下方 get_data 函数）
try:
    yf.set_ticker_session(CustomSession())
except AttributeError:
    # 如果版本太新没有这个函数，我们忽略它，改用下面的手动重试策略
    pass

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

# --- 2. 获取行情数据 (带重试和手动 Header 注入) ---
market_data = []
print("正在获取行情数据...")

def get_stock_data(ticker_symbol):
    """尝试获取股票数据，失败则重试"""
    for attempt in range(3):
        try:
            print(f"尝试获取 {ticker_symbol} (第 {attempt+1} 次)...")
            
            # 创建 Ticker 对象
            tk = yf.Ticker(ticker_symbol)
            
            # 核心技巧：直接访问 tk.history，yfinance 内部会处理
            # 如果还是被拦，通常是因为没有 Cookie 或 User-Agent
            # 我们尝试抓取历史数据
            hist = tk.history(period="5d", timeout=10)
            
            if hist is not None and not hist.empty and len(hist) >= 2:
                close_prev = hist['Close'][-2]
                close_curr = hist['Close'][-1]
                
                # 检查数据是否有效（避免 NaN）
                if pd.isna(close_prev) or pd.isna(close_curr):
                    raise ValueError("Data contains NaN")
                    
                change_pct = ((close_curr - close_prev) / close_prev) * 100
                # 假设 qty 在外部传入，这里只返回价格信息
                return {
                    "price": round(float(close_curr), 2),
                    "prev_close": round(float(close_prev), 2),
                    "change": round(float(change_pct), 2)
                }
            else:
                print(f"⚠️ {ticker_symbol} 数据为空或不足。")
                return None
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ {ticker_symbol} 失败: {error_msg}")
            
            # 如果是网络错误，等待后重试
            if "429" in error_msg or "-2" in error_msg or "Temporary" in error_msg or "Connection" in error_msg:
                wait_time = random.uniform(3, 6)
                print(f"   -> 网络波动/限流，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
            else:
                # 其他错误（如代码不存在）直接放弃
                return None
    return None

# 需要导入 pandas 来处理 NaN 检查
import pandas as pd

for stock in portfolio:
    ticker = stock['ticker']
    data = get_stock_data(ticker)
    
    if data:
        market_value = data['price'] * int(stock['qty'])
        market_data.append({
            "ticker": ticker,
            "name": stock['name'],
            "qty": stock['qty'],
            "price": data['price'],
            "change": data['change'],
            "value": round(market_value, 2)
        })
        print(f"✅ {ticker} 成功: ${data['price']} ({data['change']:+.2f}%)")
    else:
        print(f"❌ {ticker} 最终获取失败，跳过。")
        # 如果连续失败，多等一会
        time.sleep(2)

# --- 3. 构建报告内容 ---
if not market_data:
    ai_report = "⚠️ **数据获取完全失败**\n\n所有股票均无法从 Yahoo Finance 获取数据。\n可能原因：\n1. GitHub 服务器网络波动。\n2. 股票代码全部错误。\n3. Yahoo Finance 临时维护。\n\n请手动重试 Workflow 或检查代码。"
else:
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
