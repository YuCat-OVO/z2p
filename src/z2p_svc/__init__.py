"""Z2P Service - ZAI API代理服务。

本包提供了一个FastAPI应用，用于代理访问ZAI聊天API，
支持流式和非流式响应，多模态输入（文本和图片），以及多种GLM模型。

主要模块：
    - app: FastAPI应用实例和配置
    - routes: API路由定义
    - chat_service: 聊天服务核心逻辑
    - signature_generator: 请求签名生成
    - image_uploader: 图片上传处理
    - config: 应用配置管理
    - logger: 结构化日志配置
    - models: 数据模型定义
"""

__version__ = "0"