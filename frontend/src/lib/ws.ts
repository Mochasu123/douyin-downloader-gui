export type WsEventHandler = (event: { type: string; data: unknown }) => void

export class EventsSocket {
  private ws: WebSocket | null = null
  private listeners = new Set<WsEventHandler>()
  private reconnectTimer: number | null = null
  private closed = false

  connect() {
    this.closed = false
    this.openSocket()
  }

  disconnect() {
    this.closed = true
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  subscribe(handler: WsEventHandler): () => void {
    this.listeners.add(handler)
    return () => {
      this.listeners.delete(handler)
    }
  }

  private openSocket() {
    if (this.closed) return
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${window.location.host}/ws/events`
    try {
      const socket = new WebSocket(url)
      this.ws = socket
      socket.onmessage = (evt) => {
        try {
          const parsed = JSON.parse(evt.data)
          for (const listener of this.listeners) {
            listener(parsed)
          }
        } catch {
          // ignore malformed payload
        }
      }
      socket.onclose = () => {
        this.ws = null
        if (!this.closed) {
          this.reconnectTimer = window.setTimeout(() => this.openSocket(), 1500)
        }
      }
      socket.onerror = () => {
        socket.close()
      }
    } catch {
      if (!this.closed) {
        this.reconnectTimer = window.setTimeout(() => this.openSocket(), 2000)
      }
    }
  }
}

export const eventsSocket = new EventsSocket()
