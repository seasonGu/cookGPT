<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, chatStream } from '../api'
import { clearAuth, username } from '../auth'

const WELCOME = { role: 'assistant', content: '你好,我是 cookGPT 🍳 想吃什么?可以问我菜谱推荐或做法,比如「给我推荐一道不辣的家常菜」。' }

const router = useRouter()
const conversations = ref([]) // 左侧会话列表 [{id, title, updated_at}]
const activeId = ref(null) // 当前会话 id;null = 新对话
const messages = ref([{ ...WELCOME }])
const history = ref([]) // 多轮上下文(最近 3 轮),新建会话时为空
const input = ref('')
const sending = ref(false)
const listEl = ref(null)

onMounted(loadConversations)

async function loadConversations() {
  try {
    conversations.value = await api.listConversations()
  } catch (e) {
    console.error('加载会话列表失败:', e.message)
  }
}

function newChat() {
  activeId.value = null
  messages.value = [{ ...WELCOME }]
  history.value = []
}

async function selectConversation(id) {
  if (sending.value) return // 流式输出中不允许切换
  activeId.value = id
  try {
    const msgs = await api.getMessages(id)
    messages.value = msgs.length
      ? msgs.map((m) => ({ role: m.role, content: m.content }))
      : [{ ...WELCOME }]
    history.value = msgs.slice(-6)
    scrollToBottom()
  } catch (e) {
    messages.value = [{ role: 'assistant', content: `加载失败:${e.message}`, error: true }]
    history.value = []
  }
}

async function removeConversation(id) {
  if (!window.confirm('删除这个对话?')) return
  try {
    await api.deleteConversation(id)
    if (activeId.value === id) newChat()
    loadConversations()
  } catch (e) {
    window.alert(`删除失败:${e.message}`)
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true

  messages.value.push({ role: 'assistant', content: '', streaming: true })
  // 关键:从响应式数组里取回代理对象。若直接改 push 进去的原始对象,
  // Vue 不会触发重渲染,增量就一直不显示(表现为"正在思考"直到结束一次性出现)
  const reply = messages.value[messages.value.length - 1]
  scrollToBottom()

  try {
    const convId = await chatStream(text, history.value, (delta) => {
      reply.content += delta
      scrollToBottom('auto') // 增量时瞬间贴底,避免 smooth 抖动
    }, activeId.value)
    if (convId && !activeId.value) {
      activeId.value = convId // 后端自动新建的会话,记住它
      loadConversations() // 刷新侧边栏
    }
    if (!reply.error && reply.content) {
      history.value.push({ role: 'user', content: text })
      history.value.push({ role: 'assistant', content: reply.content })
      while (history.value.length > 6) history.value.shift()
    }
  } catch (e) {
    reply.error = true
    reply.content = `${reply.content}${reply.content ? '\n\n' : ''}出错了:${e.message}`
    if (e.conversationId && !activeId.value) {
      activeId.value = e.conversationId
      loadConversations()
    }
  } finally {
    // 空回答兜底:流正常结束但一个增量都没有时,给个明确提示而不是留白
    if (!reply.error && !reply.content) {
      reply.content = '抱歉,没有收到回答,请换个问法再试试。'
    }
    reply.streaming = false
    sending.value = false
    scrollToBottom()
  }
}

// Enter 发送,Shift+Enter 换行;isComposing 防止中文输入法选词时误发送
function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

function logout() {
  clearAuth()
  router.push('/login')
}

async function scrollToBottom(behavior = 'smooth') {
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior })
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <button class="new-chat" @click="newChat">＋ 新建对话</button>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === activeId }"
          @click="selectConversation(c.id)"
        >
          <span class="conv-title" :title="c.title">{{ c.title }}</span>
          <button class="conv-del" title="删除" @click.stop="removeConversation(c.id)">×</button>
        </div>
        <p v-if="!conversations.length" class="empty">还没有对话,开始提问吧</p>
      </div>
    </aside>

    <div class="chat-page">
      <header class="header">
        <div class="brand">
          <span class="logo">🍳</span>
          <span class="name">cookGPT</span>
        </div>
        <div class="user">
          <span class="username">{{ username }}</span>
          <button class="logout" @click="logout">退出</button>
        </div>
      </header>

      <main ref="listEl" class="messages">
        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="row"
          :class="msg.role"
        >
          <div class="bubble" :class="{ error: msg.error }">
            <span v-if="msg.streaming && !msg.content" class="typing">正在思考…</span>
            <template v-else>{{ msg.content }}<span v-if="msg.streaming" class="cursor">▌</span></template>
          </div>
        </div>
      </main>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="1"
          placeholder="问问 cookGPT 想吃什么,比如「给我推荐一道不辣的家常菜」"
          @keydown="onKeydown"
        />
        <button class="send" :disabled="!input.trim() || sending" @click="send">发送</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  background: #faf7f2;
}

/* ---------- 左侧会话栏 ---------- */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 14px 10px;
  background: #fdf6ec;
  border-right: 1px solid #f0e9df;
  box-sizing: border-box;
}

.new-chat {
  padding: 10px;
  border: 1px dashed #f97316;
  border-radius: 10px;
  background: #fff;
  color: #f97316;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.new-chat:hover {
  background: #fff7ed;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 12px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 10px;
  border-radius: 9px;
  font-size: 14px;
  color: #4b5563;
  cursor: pointer;
  margin-bottom: 2px;
}

.conv-item:hover {
  background: #f5ede1;
}

.conv-item.active {
  background: #ffedd5;
  color: #c2410c;
  font-weight: 500;
}

.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-del {
  visibility: hidden;
  border: none;
  background: transparent;
  color: #9ca3af;
  font-size: 15px;
  cursor: pointer;
  padding: 0 4px;
}

.conv-item:hover .conv-del {
  visibility: visible;
}

.conv-del:hover {
  color: #dc2626;
}

.empty {
  margin: 16px 0 0;
  text-align: center;
  font-size: 13px;
  color: #c4b5a5;
}

/* ---------- 聊天区 ---------- */
.chat-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: linear-gradient(90deg, #fbbf24, #f97316);
  color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 700;
}

.logo {
  font-size: 24px;
}

.user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  font-size: 14px;
  opacity: 0.95;
}

.logout {
  padding: 6px 14px;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 8px;
  background: transparent;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.logout:hover {
  background: rgba(255, 255, 255, 0.18);
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 16px;
}

.row {
  display: flex;
  margin-bottom: 14px;
}

.row.user {
  justify-content: flex-end;
}

.row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 72%;
  padding: 11px 15px;
  border-radius: 14px;
  font-size: 15px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.row.user .bubble {
  background: linear-gradient(90deg, #f97316, #ea580c);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.row.assistant .bubble {
  background: #fff;
  color: #1f2937;
  border: 1px solid #f0e9df;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.bubble.error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.typing {
  color: #9ca3af;
  font-size: 14px;
}

.cursor {
  color: #f97316;
  animation: blink 0.9s steps(1) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 14px 16px;
  background: #fff;
  border-top: 1px solid #f0e9df;
}

.composer textarea {
  flex: 1;
  resize: none;
  padding: 11px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  max-height: 120px;
  box-sizing: border-box;
}

.composer textarea:focus {
  outline: none;
  border-color: #f97316;
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.12);
}

.send {
  padding: 11px 22px;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(90deg, #f97316, #ea580c);
  transition: opacity 0.15s;
}

.send:hover:not(:disabled) {
  opacity: 0.92;
}

.send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
