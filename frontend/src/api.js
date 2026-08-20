// 后端 API 封装:自动带 JWT,401 时清登录态并跳回登录页
import { clearAuth, token } from './auth'
import router from './router'

async function request(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token.value) headers.Authorization = `Bearer ${token.value}`

  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 401) {
    clearAuth()
    router.push('/login')
    throw new Error('登录已过期,请重新登录')
  }

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    // FastAPI 校验失败的 detail 是对象数组(如 422),提取 msg 拼成可读文案
    let msg = data.detail
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(';')
    throw new Error(msg || `请求失败(${res.status})`)
  }
  return data
}

export const api = {
  register: (username, password) =>
    request('/api/auth/register', { method: 'POST', body: { username, password } }),
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: { username, password } }),
  me: () => request('/api/auth/me'),
  listConversations: () => request('/api/conversations'),
  getMessages: (id) => request(`/api/conversations/${id}/messages`),
  deleteConversation: (id) => request(`/api/conversations/${id}`, { method: 'DELETE' }),
}

/**
 * 流式问答:POST /api/chat,解析 SSE(data: {...} 行),逐段回调 onDelta。
 * history: [{role: 'user'|'assistant', content}] 多轮上下文(不含本次问题)。
 * conversationId: 继续已有会话传 id;null 则由后端自动新建。
 * 返回最终会话 id(后端自动新建时用它刷新侧边栏)。
 */
export async function chatStream(message, history, onDelta, conversationId = null) {
  const headers = { 'Content-Type': 'application/json' }
  if (token.value) headers.Authorization = `Bearer ${token.value}`

  const res = await fetch('/api/chat', {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  })

  if (res.status === 401) {
    clearAuth()
    router.push('/login')
    throw new Error('登录已过期,请重新登录')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `请求失败(${res.status})`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let convId = conversationId
  const handle = (data) => {
    if (data.conversation_id) convId = data.conversation_id
    if (data.error) {
      const e = new Error(data.error)
      e.conversationId = convId
      throw e
    }
    if (data.delta) onDelta(data.delta)
  }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() // 最后一行可能不完整,留到下一轮
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') return convId
      try {
        handle(JSON.parse(payload))
      } catch (e) {
        if (e instanceof SyntaxError) continue // 无法解析的行直接跳过
        throw e
      }
    }
  }
  // 流异常中断时,处理缓冲区里最后一行不完整事件
  if (buf.startsWith('data: ')) {
    const payload = buf.slice(6).trim()
    if (payload !== '[DONE]') {
      try {
        handle(JSON.parse(payload))
      } catch (e) {
        if (!(e instanceof SyntaxError)) throw e
      }
    }
  }
  return convId
}
