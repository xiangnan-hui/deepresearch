 
/**
 * 全局行业状态管理
 */
import { proxy, subscribe } from 'valtio'
import { request } from '@/api/request'

// 行业配置类型
export interface IndustryConfig {
  id: string
  name: string
  description: string
  // 资讯搜索关键词
  newsKeywords: string[]
  // 招投标搜索关键词
  biddingKeywords: string[]
  // 研究相关关键词
  researchKeywords: string[]
}

// 预定义的行业配置
export const INDUSTRY_CONFIGS: IndustryConfig[] = [
  {
    id: 'artificial_intelligence',
    name: '人工智能',
    description: '大模型、生成式 AI、智能体、算力与 AI 应用创新',
    newsKeywords: [
      '人工智能 最新进展',
      '大模型 发布',
      '生成式人工智能 政策',
      'AI Agent 智能体',
      '多模态模型',
      '推理模型',
      'AI 芯片 算力',
      '开源大模型',
      '人工智能 融合应用',
    ],
    biddingKeywords: [],
    researchKeywords: [
      '人工智能',
      '大模型',
      '生成式 AI',
      'AI Agent',
      '多模态',
      '推理模型',
      'AI 芯片',
    ],
  },
]

// 行业状态
export interface IndustryState {
  currentIndustryId: string
  industries: IndustryConfig[]
}

// 从 localStorage 读取
const getStoredIndustryId = (): string => {
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('selected_industry_id')
    console.log('[industry store] 从 localStorage 读取行业:', stored)
    return INDUSTRY_CONFIGS.some(i => i.id === stored) ? stored! : 'artificial_intelligence'
  }
  return 'artificial_intelligence'
}

// 创建状态
export const industryState = proxy<IndustryState>({
  currentIndustryId: getStoredIndustryId(),
  industries: INDUSTRY_CONFIGS,
})

// 订阅变化，保存到 localStorage
subscribe(industryState, () => {
  if (typeof window !== 'undefined') {
    console.log('[industry store] 保存行业到 localStorage:', industryState.currentIndustryId)
    localStorage.setItem('selected_industry_id', industryState.currentIndustryId)
  }
})

// 获取当前行业配置
export const getCurrentIndustry = (): IndustryConfig => {
  const industry = industryState.industries.find(
    (i) => i.id === industryState.currentIndustryId
  )
  console.log('[industry store] 获取当前行业:', industry?.name)
  return industry || INDUSTRY_CONFIGS[0]
}

// 切换行业
export const setCurrentIndustry = (industryId: string) => {
  console.log('[industry store] 切换行业:', industryId)
  industryState.currentIndustryId = industryState.industries.some(i => i.id === industryId) ? industryId : 'artificial_intelligence'
}

export async function loadIndustryConfig() {
  try {
    const res = await request.get<{ industries: { id: string; name: string; description: string; news_keywords: string[]; research_keywords: string[] }[] }>('/news/industries', { loading: false, errorToast: false })
    const active = res.data.industries.filter(i => i.id === 'artificial_intelligence')
    if (active.length) industryState.industries = active.map(i => ({
      id: i.id, name: i.name, description: i.description,
      newsKeywords: i.news_keywords || [], researchKeywords: i.research_keywords || [], biddingKeywords: [],
    }))
  } catch { /* Local AI defaults keep the navigation usable while the API is offline. */ }
}

// 获取行业列表（用于选择器）
export const getIndustryOptions = () => {
  return industryState.industries.map((i) => ({
    value: i.id,
    label: i.name,
    description: i.description,
  }))
}
