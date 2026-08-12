import { defineStore } from 'pinia'
import { accountsApi } from '@/api'
import { ElMessage } from 'element-plus'

export interface Account {
  id: number
  label: string
  has_pm_credential: boolean
  created_at: string
  last_used_at: string | null
  status: string
  uid?: number | null
  nickname?: string | null
}

export const useAccountStore = defineStore('account', {
  state: () => ({
    accounts: [] as Account[],
    activeId: null as number | null,
    loading: false,
  }),
  getters: {
    active: (s) => s.accounts.find((a) => a.id === s.activeId) || null,
    hasActive: (s) => s.activeId != null,
  },
  actions: {
    async refresh() {
      this.loading = true
      try {
        const [list, act] = await Promise.all([accountsApi.list(), accountsApi.active()])
        this.accounts = list
        this.activeId = act.account_id
      } finally {
        this.loading = false
      }
    },
    async setActive(id: number) {
      await accountsApi.setActive(id)
      this.activeId = id
      ElMessage.success('已切换账号')
    },
    async remove(id: number) {
      await accountsApi.remove(id)
      await this.refresh()
    },
    async validate(id: number) {
      const a = await accountsApi.validate(id)
      await this.refresh()
      return a
    },
  },
})
