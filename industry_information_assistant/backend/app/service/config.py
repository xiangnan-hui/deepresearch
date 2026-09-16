
"""服务 API 连接配置

统一从 config.settings 读取（环境变量），不再在此处维护任何硬编码密钥。
保留 get_api_config() 返回的字典键名，兼容现有调用方。
"""

from typing import Dict, Any

from config.settings import settings


class ServiceConfig:
    """Configuration for service API connections"""

    @staticmethod
    def get_api_config() -> Dict[str, Any]:
        """
        Get API configuration from the unified settings module (env-driven).

        Returns:
            Dictionary with API configuration
        """
        return {
            # RAGFlow 文档服务
            'base_url': settings.ragflow_base_url,
            'api_key': settings.ragflow_api_key,
            'default_dataset_id': settings.ragflow_default_dataset_id,
            # Serper 搜索
            'serper_api_key': settings.serper_api_key,
            # Milvus
            'milvus_host': settings.milvus_host,
            'milvus_port': settings.milvus_port,
            # DeepResearch（V1 流程）API keys
            'bochaai_api_key': settings.bocha_api_key,
            'dashscope_api_key': settings.dashscope_api_key,
            'dashscope_base_url': settings.dashscope_base_url,
        }
