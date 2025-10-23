"""消息格式转换模块。

负责将 OpenAI 格式的消息转换为智谱 AI 上游 API 格式。
处理文本消息、图片 URL、文件 URL 和多模态内容。
"""

from typing import Any

from ...models import Message, ConvertedMessages


def convert_messages(messages: list[Message]) -> ConvertedMessages:
    """转换消息格式。

    将 OpenAI Chat Completion 格式的消息转换为智谱 AI API 格式。

    **处理的内容类型:**

    - 文本消息（``role`` + ``content`` 字符串）
    - 图片 URL（``image_url`` 类型）
    - 文件 URL（``file`` 类型）

    :param messages: OpenAI 格式的消息列表
    :type messages: list[Message]
    :return: 转换后的消息和提取的文件 URL
    :rtype: ConvertedMessages

    .. code-block:: python

       messages = [
           Message(role="user", content="描述这张图"),
           Message(role="user", content=[
               {"type": "text", "text": "图片内容"},
               {"type": "image_url", "image_url": {
                   "url": "data:image/png;base64,..."
               }}
           ])
       ]

       result = convert_messages(messages)
       # result.messages: 转换后的消息列表
       # result.file_urls: ["data:image/png;base64,..."]
       # result.last_user_message_text: "图片内容"
    """
    trans_messages = []
    file_urls = []
    last_user_message_text = ""

    for message in messages:
        role = message.role
        content = message.content

        if isinstance(content, str):
            trans_messages.append({"role": role, "content": content})
            if role == "user":
                last_user_message_text = content
        elif isinstance(content, list):
            text_content = ""
            dont_append = False
            new_message: dict[str, Any] = {"role": role}

            for part in content:
                part_type = part.get("type")

                if part_type == "text":
                    text_content = part.get("text", "")

                elif part_type == "image_url":
                    file_url = part.get("image_url", {}).get("url", "")
                    if file_url:
                        file_urls.append(file_url)

                elif part_type == "file":
                    file_url = part.get("url", "")
                    if file_url:
                        file_urls.append(file_url)

            if text_content and role == "user":
                last_user_message_text = text_content

            if not dont_append and text_content:
                trans_messages.append({"role": role, "content": text_content})

    return ConvertedMessages(
        messages=trans_messages,
        file_urls=file_urls,
        last_user_message_text=last_user_message_text,
    )