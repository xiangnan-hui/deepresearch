

/**
 * 认证插件：自动添加 Token 到请求头
 */
import { IRequestPlugin } from './plugin'

const AUTH_STORAGE_KEY = 'auth'

function getToken(): string | null {
  try {
    const authData = localStorage.getItem(AUTH_STORAGE_KEY)
    if (authData) {
      const parsed = JSON.parse(authData)
      return parsed?.token || null
    }
  } catch {
    // ignore
  }
  return null
}

export const authPlugin: IRequestPlugin = {
  preinstall(instance) {
    instance.interceptors.request.use(
      (config) => {
        const token = getToken()
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )
  },
  install(instance) {
    instance.interceptors.response.use(
      response => response,
      error => {
        const status = error?.response?.status
        const requestUrl = String(error?.config?.url || '')
        if (status === 401 && !requestUrl.startsWith('/auth/')) {
          localStorage.removeItem(AUTH_STORAGE_KEY)
          // 清掉失效登录态后返回登录页，避免受保护接口持续重试 401。
          const base = String(import.meta.env.BASE_URL || '/').replace(/\/$/, '')
          const loginUrl = `${base}/login`
          if (window.location.pathname !== loginUrl) {
            window.location.assign(loginUrl)
          }
        }
        return Promise.reject(error)
      },
    )
  },
}
