import { defineStore } from 'pinia'
import localforage from 'localforage'

interface PendingData {
  id: string
  endpoint: string
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data: any
  timestamp: number
  retryCount: number
  dedupeKey: string
  nextRetryAt: number
  lastError?: string
}

interface SyncStatus {
  isOnline: boolean
  lastSyncTime: number | null
  pendingItemsCount: number
  isSyncing: boolean
  syncErrors: string[]
}

export const useOfflineStore = defineStore('offline', {
  state: (): {
    syncStatus: SyncStatus
    pendingData: PendingData[]
    cachedData: Map<string, any>
    lastActivity: number
    periodicSyncTimerId: ReturnType<typeof setInterval> | null
    onlineHandler: (() => void) | null
    offlineHandler: (() => void) | null
  } => ({
    syncStatus: {
      isOnline: typeof window !== 'undefined' ? navigator.onLine : true,
      lastSyncTime: null,
      pendingItemsCount: 0,
      isSyncing: false,
      syncErrors: []
    },
    pendingData: [],
    cachedData: new Map(),
    lastActivity: Date.now(),
    periodicSyncTimerId: null,
    onlineHandler: null,
    offlineHandler: null
  }),

  actions: {
    getCSRFToken(): string | null {
      if (typeof document === 'undefined') return null
      const name = 'csrftoken='
      const cookies = document.cookie.split(';')

      for (const rawCookie of cookies) {
        const cookie = rawCookie.trim()
        if (cookie.startsWith(name)) {
          return cookie.substring(name.length)
        }
      }
      return null
    },

    buildDedupeKey(endpoint: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', data: any) {
      return `${method}|${endpoint}|${JSON.stringify(data ?? {})}`
    },

    getErrorStatus(error: any): number | null {
      return error?.status ?? error?.statusCode ?? error?.response?.status ?? null
    },

    getErrorMessage(error: any): string {
      if (error?.data?.message) return String(error.data.message)
      if (error?.message) return String(error.message)
      return 'Unknown error'
    },

    isRetryableStatus(status: number | null): boolean {
      if (!status) return true
      if (status === 408 || status === 429) return true
      return status >= 500
    },

    async initialize() {
      localforage.config({
        name: 'HydriaApp',
        storeName: 'hydria_offline_data',
        description: 'Offline data for Hydria'
      })

      await this.loadPendingData()

      if (typeof window !== 'undefined') {
        if (this.onlineHandler) window.removeEventListener('online', this.onlineHandler)
        if (this.offlineHandler) window.removeEventListener('offline', this.offlineHandler)

        this.onlineHandler = () => {
          this.handleOnline()
        }
        this.offlineHandler = () => {
          this.handleOffline()
        }

        window.addEventListener('online', this.onlineHandler)
        window.addEventListener('offline', this.offlineHandler)
        window.addEventListener('click', () => this.updateActivity())
        window.addEventListener('keypress', () => this.updateActivity())
      }

      if (this.syncStatus.isOnline) {
        this.startPeriodicSync()
      }
    },

    async handleOnline() {
      this.syncStatus.isOnline = true
      await new Promise(resolve => setTimeout(resolve, 1000))
      await this.syncPendingData()
      this.startPeriodicSync()
    },

    handleOffline() {
      this.syncStatus.isOnline = false
    },

    updateActivity() {
      this.lastActivity = Date.now()
    },

    async addPendingData(endpoint: string, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', data: any) {
      const dedupeKey = this.buildDedupeKey(endpoint, method, data)
      const existing = this.pendingData.find(item => item.dedupeKey === dedupeKey)

      if (existing) {
        existing.timestamp = Date.now()
        existing.lastError = undefined
        existing.nextRetryAt = Date.now()
        await this.savePendingData()
        return
      }

      const pendingItem: PendingData = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`,
        endpoint,
        method,
        data,
        timestamp: Date.now(),
        retryCount: 0,
        dedupeKey,
        nextRetryAt: Date.now()
      }

      this.pendingData.push(pendingItem)
      this.syncStatus.pendingItemsCount = this.pendingData.length
      await this.savePendingData()

      if (this.syncStatus.isOnline && !this.syncStatus.isSyncing) {
        setTimeout(() => this.syncPendingData(), 1000)
      }
    },

    async syncPendingData() {
      if (!this.syncStatus.isOnline || this.syncStatus.isSyncing || this.pendingData.length === 0) {
        return
      }

      this.syncStatus.isSyncing = true
      this.syncStatus.syncErrors = []

      const itemsToRemove: string[] = []
      const { $fetch } = useNuxtApp()
      const now = Date.now()

      for (const item of this.pendingData) {
        if (item.nextRetryAt > now) continue

        try {
          const config = useRuntimeConfig()
          const csrfToken = this.getCSRFToken()
          const url = `${config.public.apiBaseUrl}${item.endpoint}`

          await $fetch(url, {
            method: item.method,
            body: item.data,
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
            }
          })

          itemsToRemove.push(item.id)
        } catch (error: any) {
          const status = this.getErrorStatus(error)
          const message = this.getErrorMessage(error)
          item.retryCount += 1

          if (!this.isRetryableStatus(status) || item.retryCount >= 5) {
            itemsToRemove.push(item.id)
            this.syncStatus.syncErrors.push(
              `Definitive failure (${status ?? 'n/a'}): ${item.method} ${item.endpoint} - ${message}`
            )
          } else {
            const backoffMs = Math.min(5 * 60 * 1000, (2 ** item.retryCount) * 1000)
            item.nextRetryAt = Date.now() + backoffMs
            item.lastError = `${status ?? 'network'}: ${message}`
          }
        }

        await new Promise(resolve => setTimeout(resolve, 300))
      }

      this.pendingData = this.pendingData.filter(item => !itemsToRemove.includes(item.id))
      this.syncStatus.pendingItemsCount = this.pendingData.length
      this.syncStatus.lastSyncTime = Date.now()
      await this.savePendingData()
      this.syncStatus.isSyncing = false
    },

    async savePendingData() {
      try {
        await localforage.setItem('pendingData', this.pendingData)
        await localforage.setItem('syncStatus', {
          lastSyncTime: this.syncStatus.lastSyncTime,
          syncErrors: this.syncStatus.syncErrors
        })
      } catch (_error) {
        // ignore storage transient errors
      }
    },

    async loadPendingData() {
      try {
        const savedPendingData = await localforage.getItem('pendingData') as PendingData[] | null
        if (savedPendingData) {
          this.pendingData = savedPendingData.map(item => ({
            ...item,
            dedupeKey: item.dedupeKey || this.buildDedupeKey(item.endpoint, item.method, item.data),
            nextRetryAt: item.nextRetryAt || Date.now()
          }))
          this.syncStatus.pendingItemsCount = this.pendingData.length
        }

        const savedSyncStatus = await localforage.getItem('syncStatus') as {
          lastSyncTime?: number | null
          syncErrors?: string[]
        } | null

        if (savedSyncStatus) {
          this.syncStatus.lastSyncTime = savedSyncStatus.lastSyncTime ?? null
          this.syncStatus.syncErrors = savedSyncStatus.syncErrors || []
        }
      } catch (_error) {
        // ignore storage transient errors
      }
    },

    async cacheData(key: string, data: any) {
      this.cachedData.set(key, data)
      try {
        await localforage.setItem(`cache_${key}`, data)
      } catch (_error) {
        // ignore storage transient errors
      }
    },

    async getCachedData(key: string) {
      if (this.cachedData.has(key)) {
        return this.cachedData.get(key)
      }

      try {
        const data = await localforage.getItem(`cache_${key}`)
        if (data) this.cachedData.set(key, data)
        return data
      } catch (_error) {
        return null
      }
    },

    startPeriodicSync() {
      if (this.periodicSyncTimerId) {
        clearInterval(this.periodicSyncTimerId)
      }

      this.periodicSyncTimerId = setInterval(() => {
        const now = Date.now()
        const inactiveTime = now - this.lastActivity
        if (this.syncStatus.isOnline && inactiveTime < 30 * 60 * 1000) {
          this.syncPendingData()
        }
      }, 5 * 60 * 1000)

      if (typeof window !== 'undefined') {
        window.addEventListener('beforeunload', () => {
          if (this.periodicSyncTimerId) {
            clearInterval(this.periodicSyncTimerId)
            this.periodicSyncTimerId = null
          }
        })
      }
    },

    async clearOfflineData() {
      this.pendingData = []
      this.cachedData.clear()
      this.syncStatus.pendingItemsCount = 0
      this.syncStatus.syncErrors = []
      await localforage.clear()
    }
  },

  getters: {
    isOnline: state => state.syncStatus.isOnline,
    pendingCount: state => state.syncStatus.pendingItemsCount,
    lastSyncFormatted: state => {
      if (!state.syncStatus.lastSyncTime) return 'Never'
      return new Date(state.syncStatus.lastSyncTime).toLocaleString('fr-FR')
    },
    isSyncing: state => state.syncStatus.isSyncing,
    syncErrors: state => state.syncStatus.syncErrors
  }
})
