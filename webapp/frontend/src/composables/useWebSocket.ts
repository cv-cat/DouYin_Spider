import { ref, onUnmounted } from 'vue'

/** 通用 WebSocket 连接(自动重连)。返回事件 ref 与控制方法。 */
export function useWebSocket(path: string) {
  const events = ref<any[]>([])
  const connected = ref(false)
  let ws: WebSocket | null = null
  let stopped = false
  let reconnectTimer: number | null = null

  function connect() {
    if (stopped) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}${path}`
    ws = new WebSocket(url)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      if (!stopped) reconnectTimer = window.setTimeout(connect, 2000)
    }
    ws.onerror = () => { ws?.close() }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        events.value.push(msg)
        if (events.value.length > 500) events.value.splice(0, events.value.length - 500)
      } catch (e) { /* ignore */ }
    }
  }

  function close() {
    stopped = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  }

  function clear() { events.value = [] }

  connect()
  onUnmounted(close)

  return { events, connected, close, clear }
}
