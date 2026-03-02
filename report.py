import os
import csv
import requests
from datetime import datetime, timedelta
import time
import random
from dotenv import load_dotenv

# # 加载 .env 文件中的环境变量
# load_dotenv()

# # --- 配置 ---
# DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
# WECHAT_WEBHOOK = os.getenv("WECHAT_WEBHOOK")
# DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# --- API提供商配置 ---
# Alpha Vantage API
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "your_alpha_vantage_key_here")
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# 新闻搜索相关
import json
from urllib.parse import urlencode

# 固定使用 Alpha Vantage
STOCK_API_PROVIDER = "alpha_vantage"

def get_stock_data_alpha_vantage(ticker_symbol):
    """通过Alpha Vantage API获取股票数据"""
    url = f"{ALPHA_VANTAGE_BASE_URL}?function=GLOBAL_QUOTE&symbol={ticker_symbol}&apikey={ALPHA_VANTAGE_API_KEY}"

    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            quote = data.get("Global Quote")
            if quote:
                current_price = float(quote.get("05. price", 0))
                prev_close = float(quote.get("08. previous close", 0))

                if current_price > 0 and prev_close > 0:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    return {
                        "price": round(current_price, 2),
                        "prev_close": round(prev_close, 2),
                        "change": round(change_pct, 2)
                    }
        elif response.status_code == 429:
            print("   -> Alpha Vantage API速率限制")
            time.sleep(60)  # Alpha Vantage免费版每分钟最多5次请求
        else:
            print(f"   -> Alpha Vantage API错误: {response.status_code}")
    except Exception as e:
        print(f"   -> Alpha Vantage请求失败: {str(e)}")

    return None

def get_stock_data(ticker_symbol):
    """获取股票数据 - 只使用 Alpha Vantage"""
    print(f"正在获取 {ticker_symbol} 的数据 - 使用 Alpha Vantage API")

    result = get_stock_data_alpha_vantage(ticker_symbol)

    if result:
        return result
    else:
        wait_time = random.uniform(10, 20)
        print(f"   -> 等待 {wait_time:.1f} 秒后重试...")
        time.sleep(wait_time)

        # 重试一次
        return get_stock_data_alpha_vantage(ticker_symbol)

def search_news_for_stocks(portfolio_data):
    """搜索每只股票当天的股市变动相关资讯 - 每只股票最多搜索2次"""
    news_data = {}
    print("正在搜索相关股票新闻...")

    # 获取今天的日期
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"正在搜索 {today} 的股市变动相关资讯...")

    for stock in portfolio_data:
        ticker = stock['ticker']
        name = stock['name']
        print(f"正在为 {ticker} ({name}) 搜索当天股市变动相关资讯...")

        found_articles = []
        attempts = 0
        max_attempts = 2  # 每只股票最多搜索2次

        # 尽量只进行一次有效查询
        while attempts < max_attempts and len(found_articles) == 0:
            attempts += 1
            print(f"  第 {attempts} 次搜索 {ticker}...")

            # 统一使用综合性的查询策略，增加首次成功概率
            if attempts == 1:
                # 第一次搜索：综合性查询策略，覆盖价格变动、市场新闻、交易量、盈利报告等多个方面
                query = f"{ticker} {name} stock price change market news trading volume earnings financial report today"
            else:
                # 第二次搜索（后备）：更广泛的行业和市场影响
                query = f"{ticker} {name} trading volume earnings news today"

            try:
                params = {
                    "engine": "google",
                    "q": query,
                    "api_key": os.getenv("SERPAPI_API_KEY"),
                    "gl": "US",
                    "hl": "en",
                    "num": 3,
                    "tbs": f"qdr:d"  # 限制为今天(today)的新闻
                }

                # 构造API URL
                base_url = "https://serpapi.com/search"
                query_string = urlencode(params)
                search_url = f"{base_url}?{query_string}"

                response = requests.get(search_url, timeout=30)
                if response.status_code == 200:
                    results = response.json()

                    # 提取新闻结果
                    if "organic_results" in results:
                        articles = results["organic_results"]

                        # 查找与该股票相关的新闻
                        for article in articles:
                            title = article.get("title", "")
                            snippet = article.get("snippet", "")
                            link = article.get("link", "")
                            source = article.get("source", "Unknown Source")

                            # 检查标题或摘要是否提及该股票或相关关键词
                            ticker_mentioned = (ticker.lower() in title.lower() or
                                              ticker.lower() in snippet.lower() or
                                              name.split()[0].lower() in title.lower() or
                                              name.split()[0].lower() in snippet.lower())

                            # 检查是否涉及股市变动、价格变动等相关关键词
                            market_related = any(keyword in title.lower() or keyword in snippet.lower()
                                               for keyword in ["stock", "price", "trading", "market",
                                                             "earnings", "report", "financial",
                                                             "investor", "shares", "valuation",
                                                             "bull", "bear", "gains", "losses",
                                                             "up", "down", "rise", "fall", "change"])

                            # 只有当提及股票且与股市相关时才添加
                            if title and snippet and ticker_mentioned and market_related:
                                article_obj = {
                                    "title": title,
                                    "snippet": snippet,
                                    "link": link,
                                    "source": source,
                                    "query_used": query
                                }

                                # 避免重复添加相同的文章
                                if article_obj not in found_articles:
                                    found_articles.append(article_obj)

                        if found_articles:
                            print(f"  第 {attempts} 次搜索找到 {len(found_articles)} 条相关资讯")
                        else:
                            print(f"  第 {attempts} 次搜索未找到相关资讯")

                else:
                    print(f"  搜索 {ticker} 新闻时HTTP错误: {response.status_code}")

            except Exception as e:
                print(f"  搜索 {ticker} 新闻时出错: {str(e)}")

            # 在两次搜索之间稍作停顿，避免API限制
            if attempts < max_attempts:
                time.sleep(2)

        # 存储找到的资讯，如果没有找到则标记
        if found_articles:
            # 每只股票最多存储2条最有价值的新闻
            news_data[ticker] = found_articles[:2]
        else:
            # 如果没有找到任何相关信息，记录状态
            news_data[ticker] = [{
                "title": "当天无相关资讯",
                "snippet": f"未能找到{ticker}在{today}的相关股市变动资讯",
                "link": "",
                "source": "System",
                "query_used": "None"
            }]

    return news_data

def format_news_summary(news_data):
    """格式化新闻摘要"""
    if not news_data:
        return "未能获取相关新闻信息。"

    news_summary = "🔍 **相关新闻资讯**\n\n"

    for ticker, articles in news_data.items():
        news_summary += f"📌 **{ticker} 重要新闻**:\n"
        for i, article in enumerate(articles[:2], 1):  # 每只股票最多显示2条新闻
            if article['title'] not in ["昨夜无重要新闻", "新闻搜索失败", "未搜索"]:
                importance_mark = "🔥" if article.get('is_important', False) else "📰"
                news_summary += f"  {i}. {importance_mark}【{article['source']}】{article['title']}\n"
                news_summary += f"     📝 {article['snippet']}\n"
                if article['link']:
                    news_summary += f"     🔗 {article['link']}\n"
                news_summary += "\n"
            else:
                news_summary += f"  {i}. {article['snippet']}\n\n"
        news_summary += "\n"

    return news_summary

def format_portfolio_ui(market_data):
    """格式化投资组合UI显示（适用于即时通讯软件）"""
    if not market_data:
        return "没有可用的持仓数据。"

    ui_output = "💼 **投资组合概览**\n\n"

    for stock in market_data:
        # 确定涨跌符号和颜色
        change = stock['change']
        change_str = f"{change:+.2f}%"
        emoji = "📈" if change >= 0 else "📉"

        # 使用颜色emoji表示涨跌：绿色表示上涨，红色表示下跌
        color_indicator = "🟢" if change >= 0 else "🔴"

        ui_output += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} **{stock['ticker']}** - {stock['name']}\n"
            f"📊 持有: {stock['qty']} 股  |  💰 当价: ${stock['price']}\n"
            f"🗓️ 昨收: ${stock['prev_close']}  |  {color_indicator} 涨跌: {change_str}\n"
            f"🏦 市值: ${stock['value']}\n"
        )

    # 添加总计信息
    total_value = sum(d['value'] for d in market_data)
    ui_output += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ui_output += f"📈 **总市值: ${total_value:,.2f}**\n\n"

    return ui_output

# --- 1. 读取持仓 ---
portfolio = []
try:
    with open('portfolio.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            portfolio.append(row)
except Exception as e:
    print(f"错误：读取 CSV 失败: {e}")
    exit(1)

# --- 2. 获取行情数据 ---
market_data = []
print("正在使用 Alpha Vantage API 获取行情数据...")

# 逐个获取股票数据
for i, stock in enumerate(portfolio):
    ticker = stock['ticker']
    print(f"正在处理 {ticker} ({stock['name']}) - {i+1}/{len(portfolio)}")

    data = get_stock_data(ticker)

    if data:
        market_value = data['price'] * int(stock['qty'])
        market_data.append({
            "ticker": ticker,
            "name": stock['name'],
            "qty": stock['qty'],
            "price": data['price'],
            "prev_close": data['prev_close'],
            "change": data['change'],
            "value": round(market_value, 2)
        })
        print(f"成功：{ticker} - ${data['price']} ({data['change']:+.2f}%)")
    else:
        print(f"失败：{ticker} 获取数据失败，跳过。")

    # 在每个请求之间添加延迟以避免过于频繁的请求
    if i < len(portfolio) - 1:  # 不在最后一个元素后等待
        delay = random.uniform(12, 18)  # 减少延迟以降低总等待时间
        print(f"   -> 等待 {delay:.1f} 秒后继续下一个请求...")
        time.sleep(delay)

# --- 3. 获取相关新闻 ---
news_data = {}
if market_data:
    print("正在获取相关新闻信息...")
    news_data = search_news_for_stocks(market_data)

# --- 4. 构建报告内容 ---
if not market_data:
    ai_report = f"""⚠️ **数据获取完全失败**

所有股票均无法从 Alpha Vantage API 获取数据。
可能原因：
1. 网络连接问题。
2. 所有股票代码无效或不存在。
3. API密钥缺失或无效。
4. API配额已用尽。
5. API提供商临时服务问题。

请检查您的 Alpha Vantage API 密钥和配额。"""
else:
    # 格式化投资组合UI
    portfolio_ui = format_portfolio_ui(market_data)

    # 添加新闻信息到提示词
    news_summary = format_news_summary(news_data)

    prompt = f"""
    你是一位专业的美股投资顾问。请根据以下数据和新闻信息，为我生成一份【{datetime.now().strftime('%Y年%m月%d日')}】的美股晨报。

    {portfolio_ui}

    {news_summary}

    要求：
    1. **市场总览**：一句话总结昨夜整体市场表现。
    2. **个股点评**：对每只股票结合新闻信息简要分析涨跌原因。
    3. **新闻影响**：分析新闻对各股票价格变动的可能影响。
    4. **操作建议**：基于数据分析和新闻信息给出具体操作建议（持有/减仓/加仓/关注）。
    5. **风险提示**：指出可能影响投资决策的风险因素。
    6. **风格**：专业、简洁，直接说结论。
    7. **格式**：使用 Markdown 格式，适合在即时通讯软件中阅读，使用适当的emoji和分隔符。
    """

    # --- 5. 调用 DeepSeek AI ---
    print("正在请求 DeepSeek AI...")
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1500
    }

    ai_report = ""
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        ai_report = response.json()['choices'][0]['message']['content']
    except Exception as e:
        ai_report = f"⚠️ AI 分析失败：{str(e)}\n\n{format_portfolio_ui(market_data)}\n\n新闻信息:\n{format_news_summary(news_data)}"

# --- 6. 推送到企业微信 ---
print("正在发送消息...")
if len(ai_report) > 3800:
    ai_report = ai_report[:3800] + "\n...(内容过长)"

wechat_payload = {
    "msgtype": "markdown",
    "markdown": {
        "content": f"🇺🇸 **美股晨报**\n📅 日期：{datetime.now().strftime('%Y-%m-%d')}\n\n{ai_report}"
    }
}

try:
    resp = requests.post(WECHAT_WEBHOOK, json=wechat_payload, timeout=10)
    if resp.status_code == 200:
        print("[OK] 发送成功！")
    else:
        print(f"[ERR] 发送失败: {resp.text}")
except Exception as e:
    print(f"[ERR] 网络错误: {e}")
