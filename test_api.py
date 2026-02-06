import os
from openai import OpenAI
import httpx

# ================= 配置区域 =================
# 1. 填入你的 OpenRouter API Key
API_KEY = "sk-e65135cb5b7944009d5b549f30eece0e" 

# 2. 填入你想测试的模型 ID (建议先用 DeepSeek 或 Google 免费模型测通)
# 推荐: "deepseek/deepseek-chat" 或 "google/gemini-2.0-flash-exp:free"
MODEL_NAME = "deepseek-chat" 
# ===========================================

def test_connection():
    print(f"🚀 正在连接 OpenRouter...")
    print(f"🔑 Key: {API_KEY[:10]}******")
    print(f"🤖 Model: {MODEL_NAME}")
    print("-" * 40)

    try:
        # 初始化客户端
        client = OpenAI(
            base_url="https://api.deepseek.com/v1",
            api_key=API_KEY,
            http_client=httpx.Client(timeout=30.0) # 设置30秒超时
        )

        # 发送简单请求
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "user", "content": "Hello! Are you working? Reply in one word."}
            ],
        )

        # 获取结果
        result = response.choices[0].message.content
        print(f"✅ 测试成功！模型回复: {result}")
        return True

    except Exception as e:
        print(f"❌ 测试失败！")
        error_msg = str(e)
        
        # 智能诊断错误原因
        if "401" in error_msg:
            print("👉 原因诊断: API Key 无效。请检查是否有多余空格，或 Key 是否已过期。")
        elif "404" in error_msg:
            print(f"👉 原因诊断: 模型 '{MODEL_NAME}' 不存在。请去 OpenRouter 模型列表复制正确的 ID。")
        elif "402" in error_msg:
            print("👉 原因诊断: 余额不足。虽然部分模型免费，但有些需要账户里有少许余额。")
        else:
            print(f"👉 详细错误: {error_msg}")
        return False

if __name__ == "__main__":
    test_connection()