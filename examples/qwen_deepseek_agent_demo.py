"""Example: Connect knime-viz-toolkit to Qwen (通义千问 / DashScope) or DeepSeek via OpenAI-compatible API.

Prerequisites:
    pip install openai
    # Set DASHSCOPE_API_KEY (for Qwen) or DEEPSEEK_API_KEY (for DeepSeek)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from knime_viz_toolkit import KnimeVizAgentToolkit

WORKFLOW = str(Path(__file__).resolve().parents[2] / "knime" / "Bike_Sharing_Master_Workflow_EXECUTED.knwf")


def run_with_qwen_or_deepseek(user_prompt: str) -> None:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError:
        print("Install the OpenAI SDK first: pip install openai")
        print("Below are the exact tool schemas ready for Qwen / DeepSeek / Kimi:")
        tk = KnimeVizAgentToolkit()
        print(json.dumps(tk.get_openai_tools()[:2], indent=2, ensure_ascii=False))
        return

    # Default: Alibaba Cloud DashScope (通义千问 Qwen)
    # For DeepSeek: base_url="https://api.deepseek.com", model="deepseek-chat"
    # For Kimi (Moonshot): base_url="https://api.moonshot.cn/v1", model="moonshot-v1-8k"
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Please set DASHSCOPE_API_KEY (通义千问) or DEEPSEEK_API_KEY in your environment.")

    is_deepseek = bool(os.getenv("DEEPSEEK_API_KEY") and not os.getenv("DASHSCOPE_API_KEY"))
    base_url = "https://api.deepseek.com" if is_deepseek else "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = "deepseek-chat" if is_deepseek else "qwen-plus"

    client = OpenAI(api_key=api_key, base_url=base_url)
    toolkit = KnimeVizAgentToolkit(cache_workflows=True)
    tools = toolkit.get_openai_tools()

    messages: list[dict] = [
        {
            "role": "system",
            "content": "You are a data visualization assistant with tools to inspect and render KNIME workflows.",
        },
        {"role": "user", "content": user_prompt},
    ]

    try:
        for _ in range(6):
            resp = client.chat.completions.create(model=model, messages=messages, tools=tools)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                print("\n=== Assistant Reply ===")
                print(msg.content)
                break

            for tc in msg.tool_calls:
                print(f"[Tool Call] {tc.function.name}({tc.function.arguments})")
                result_json = toolkit.call_tool_json(tc.function.name, tc.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_json,
                    }
                )
    finally:
        toolkit.close()


if __name__ == "__main__":
    prompt = (
        f"请帮我检查 KNIME 工作流 {WORKFLOW}，并用 dark_transparent 透明底深色 PPT 主题"
        "将所有图表渲染到 ./qwen_out 目录，最后告诉我生成了几张图以及模型的 R2 表现。"
    )
    run_with_qwen_or_deepseek(prompt)
