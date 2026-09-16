import asyncio
from typing import Dict, Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.status import HTTP_200_OK, HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.orm import Session

from core.database import get_db
from models.chat import ChatAttachment
from service import WebSearchService, ChatService, SessionService, ServiceConfig
from service.ai_knowledge_service import retrieve_personal_content
from router.auth_router import get_current_user_required
from models.user import User
from schemas import ChatRequest, LegacySessionResponse, ChatWithAttachmentsRequest

# Create router instance
router = APIRouter(prefix="/chat", tags=["chat"])

# Get service instances
def get_services():
    config = ServiceConfig.get_api_config()
    web_service = WebSearchService(api_key=config.get('serper_api_key'))
    session_service = SessionService()
    chat_service = ChatService(web_service, session_service)
    return {
        "chat_service": chat_service,
        "session_service": session_service,
    }



@router.post("/session", response_model=LegacySessionResponse, status_code=HTTP_200_OK)
async def create_session(
    services: Dict[str, Any] = Depends(get_services),
    current_user: User = Depends(get_current_user_required),
):
    """
    创建新的聊天会话

    Returns:
        新创建的会话信息
    """
    session_service = services["session_service"]

    try:
        session_data = session_service.create_session()
        return LegacySessionResponse(**session_data)
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建会话失败: {str(e)}"
        )

@router.post("/completion", status_code=HTTP_200_OK)
async def chat_completion(
    request: ChatRequest,
    services: Dict[str, Any] = Depends(get_services),
    current_user: User = Depends(get_current_user_required),
):
    """
    聊天补全接口，结合当前用户的个人知识库和Web搜索进行问答，支持研究任务追问

    Args:
        request: 包含用户问题和会话信息的请求体

    Returns:
        流式响应，包含检索内容和模型生成内容
    """
    chat_service = services["chat_service"]
    session_service = services["session_service"]

    # Fast Agent 路径：只读取共享状态与摘要，不等待或重启 Deep Research。
    if request.research_id:
        try:
            from harness.research_runtime import get_research_runtime
        except ImportError:
            from app.harness.research_runtime import get_research_runtime
        runtime = get_research_runtime()
        research_state = await runtime.states.get(request.research_id)
        if not research_state or research_state.get("user_id") != str(current_user.id):
            raise HTTPException(status_code=404, detail="Research task not found")
        try:
            result = await runtime.fast_agent.respond(request.research_id, request.question)
        except KeyError:
            raise HTTPException(status_code=404, detail="Research task not found")
        answer = result["answer"]

        async def generate_research_answer():
            import json
            yield f"data: {json.dumps({'role': 'assistant', 'content': answer, 'intent': result.get('intent')}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate_research_answer(), media_type="text/event-stream")

    # 验证会话ID（如果提供）
    if request.session_id:
        session = session_service.get_session(request.session_id)
        if not session:
            # 如果会话不存在，创建新会话
            session_data = session_service.create_session()
            request.session_id = session_data["session_id"]

    # 创建异步生成器函数
    async def generate_response():
        try:
            # 从当前用户的知识库检索
            policy_docs = []
            if request.search_knowledge:
                # 复用个人知识库的 UUID 集合与文档状态过滤
                retrieved_data = await asyncio.to_thread(
                    retrieve_personal_content, request.question, str(current_user.id)
                )

                # 转换数据格式以适配现有系统
                policy_docs = []
                for item in retrieved_data:
                    policy_docs.append({
                        "id": item["id"],
                        "content": item["content_with_weight"],
                        "source": f"{item['document_name']} (ID: {item['document_id']})",
                        "document_id": item["document_id"],
                        "document_name": item["document_name"]
                    })

            # 从Web搜索检索信息
            web_docs = []
            if request.search_web:
                web_docs = chat_service.retrieve_from_web(
                    question=request.question
                )

            # 合并文档并重排
            all_docs = policy_docs + web_docs
            reranked_docs = chat_service.rerank_documents(
                question=request.question,
                documents=all_docs
            )

            # 生成流式回答
            for message_chunk in chat_service.get_chat_completion(
                session_id=request.session_id,
                question=request.question,
                retrieved_content=reranked_docs
            ):
                yield message_chunk

        except Exception as e:
            # 错误处理
            error_message = f"event: error\ndata: {str(e)}\n\n"
            yield error_message

    # 返回流式响应
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream"
    )


@router.post("/completion/v3", status_code=HTTP_200_OK)
async def chat_completion_with_attachments(
    request: ChatWithAttachmentsRequest,
    db: Session = Depends(get_db),
    services: Dict[str, Any] = Depends(get_services),
    current_user: User = Depends(get_current_user_required),
):
    """
    聊天补全接口v3版本，支持附件的问答

    附件内容会被提取并加入到上下文中，用于回答问题。

    Args:
        request: 包含用户问题、附件ID列表和会话信息的请求体

    Returns:
        流式响应，包含检索内容和模型生成内容
    """
    chat_service = services["chat_service"]
    session_service = services["session_service"]

    # 验证会话ID（如果提供）
    if request.session_id:
        session = session_service.get_session(request.session_id)
        if not session:
            session_data = session_service.create_session()
            request.session_id = session_data["session_id"]

    # 获取附件内容
    attachment_contents = []
    if request.attachment_ids:
        for att_id in request.attachment_ids:
            try:
                att_uuid = UUID(att_id)
                att = db.query(ChatAttachment).filter(ChatAttachment.id == att_uuid).first()
                if att and att.content_text and att.status == "completed":
                    attachment_contents.append({
                        "filename": att.filename,
                        "content": att.content_text[:10000],  # 限制每个附件内容长度
                    })
            except ValueError:
                continue

    async def generate_response():
        try:
            # 从政策文档索引检索
            policy_docs = []
            if request.search_knowledge:
                retrieved_data = await asyncio.to_thread(
                    retrieve_personal_content, request.question, str(current_user.id)
                )
                for item in retrieved_data:
                    policy_docs.append({
                        "id": item["id"],
                        "content": item["content_with_weight"],
                        "source": f"{item['document_name']} (ID: {item['document_id']})",
                        "document_id": item["document_id"],
                        "document_name": item["document_name"]
                    })

            # 从Web搜索检索信息
            web_docs = []
            if request.search_web:
                web_docs = chat_service.retrieve_from_web(
                    question=request.question
                )

            # 合并文档并重排
            all_docs = policy_docs + web_docs
            reranked_docs = chat_service.rerank_documents(
                question=request.question,
                documents=all_docs
            )

            # 构建附件上下文
            attachment_context = ""
            if attachment_contents:
                attachment_context = "\n\n=== 用户上传的附件内容 ===\n"
                for att in attachment_contents:
                    attachment_context += f"\n--- {att['filename']} ---\n{att['content']}\n"
                attachment_context += "\n=== 附件内容结束 ===\n\n"

            # 修改问题，加入附件上下文
            enhanced_question = request.question
            if attachment_context:
                enhanced_question = f"用户问题：{request.question}\n\n请结合以下上传的附件内容来回答问题：{attachment_context}"

            # 生成流式回答
            for message_chunk in chat_service.get_chat_completion(
                session_id=request.session_id,
                question=enhanced_question,
                retrieved_content=reranked_docs
            ):
                yield message_chunk

        except Exception as e:
            error_message = f"event: error\ndata: {str(e)}\n\n"
            yield error_message

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream"
    )
