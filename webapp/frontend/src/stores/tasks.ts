import { defineStore } from 'pinia'
import { tasksApi } from '@/api'

export interface Task {
  id: string
  kind: string
  status: string
  progress: number
  result: any
  error: string | null
  created_at: string
  finished_at: string | null
  params: Record<string, any>
}

export const useTaskStore = defineStore('tasks', {
  state: () => ({
    tasks: [] as Task[],
    ws: null as WebSocket | null,
    subscribed: false,
  }),
  actions: {
    async refresh() {
      try {
        this.tasks = await tasksApi.list()
      } catch (e) { /* ignore */ }
    },
    subscribe() {
      if (this.subscribed) return
      this.subscribed = true
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      this.ws = new WebSocket(`${proto}://${location.host}/api/tasks/ws`)
      this.ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'task.snapshot') {
            this.tasks = msg.data
          } else {
            const t: Task = msg.data
            const idx = this.tasks.findIndex((x) => x.id === t.id)
            if (idx >= 0) this.tasks[idx] = t
            else this.tasks.unshift(t)
          }
        } catch (e) { /* ignore */ }
      }
      this.ws.onclose = () => {
        this.subscribed = false
        setTimeout(() => this.subscribe(), 2000)
      }
    },
    async cancel(id: string) { await tasksApi.cancel(id) },
    async remove(id: string) {
      await tasksApi.remove(id)
      this.tasks = this.tasks.filter((t) => t.id !== id)
    },
    get(id: string) { return this.tasks.find((t) => t.id === id) },
  },
})
