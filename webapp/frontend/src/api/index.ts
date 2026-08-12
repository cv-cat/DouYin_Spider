import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

http.interceptors.response.use(
  (r) => r,
  (e) => {
    const msg = e?.response?.data?.detail || e?.message || '请求失败'
    return Promise.reject(new Error(msg))
  },
)

// ---------- 账号 ----------
export const accountsApi = {
  list: () => http.get('/accounts').then((r) => r.data),
  active: () => http.get('/accounts/active').then((r) => r.data),
  setActive: (id: number) => http.put(`/accounts/${id}/active`).then((r) => r.data),
  remove: (id: number) => http.delete(`/accounts/${id}`).then((r) => r.data),
  patch: (id: number, label: string) => http.patch(`/accounts/${id}`, { label }).then((r) => r.data),
  validate: (id: number) => http.post(`/accounts/${id}/validate`).then((r) => r.data),
  qrStart: () => http.post('/accounts/login/qr/start').then((r) => r.data),
  qrPoll: (tempId: string) => http.get('/accounts/login/qr/poll', { params: { temp_id: tempId } }).then((r) => r.data),
  cookieLogin: (cookies: string, label: string, extract: boolean) =>
    http.post('/accounts/login/cookie', { cookies, label, extract_credential: extract }).then((r) => r.data),
  headedLogin: (timeout = 180) => http.post('/accounts/login/headed', null, { params: { timeout } }).then((r) => r.data),
}

// ---------- 采集 ----------
export const crawlApi = {
  work: (url: string) => http.get('/crawl/work', { params: { url } }).then((r) => r.data),
  userInfo: (userUrl: string) => http.get('/crawl/user-info', { params: { user_url: userUrl } }).then((r) => r.data),
  userWorks: (body: any) => http.post('/crawl/user-works', body).then((r) => r.data),
  comments: (url: string) => http.get('/crawl/comments', { params: { url } }).then((r) => r.data),
  followers: (userId: string, secId: string, num = 20) => http.get('/crawl/followers', { params: { user_id: userId, sec_id: secId, num } }).then((r) => r.data),
  following: (userId: string, secId: string, num = 20) => http.get('/crawl/following', { params: { user_id: userId, sec_id: secId, num } }).then((r) => r.data),
  favorites: (secId: string, maxCursor = '0', num = '18') => http.get('/crawl/favorites', { params: { sec_id: secId, max_cursor: maxCursor, num } }).then((r) => r.data),
  notices: (num = 20) => http.get('/crawl/notices', { params: { num } }).then((r) => r.data),
  feed: (count = '20') => http.get('/crawl/feed', { params: { count } }).then((r) => r.data),
  collectList: () => http.get('/crawl/collect-list').then((r) => r.data),
  rank: (roomId: string, anchorId: string, secAnchorId: string) => http.get('/crawl/rank', { params: { room_id: roomId, anchor_id: anchorId, sec_anchor_id: secAnchorId } }).then((r) => r.data),
}

// ---------- 搜索 ----------
export const searchApi = {
  work: (body: any) => http.post('/search/work', body).then((r) => r.data),
  user: (query: string, num = 20) => http.post('/search/user', { query, num }).then((r) => r.data),
  live: (query: string, num = 20) => http.post('/search/live', { query, num }).then((r) => r.data),
}

// ---------- 直播 ----------
export const liveApi = {
  start: (roomId: string) => http.post('/live/start', { room_id: roomId }).then((r) => r.data),
  stop: (roomId: string) => http.post('/live/stop', { room_id: roomId }).then((r) => r.data),
  status: () => http.get('/live/status').then((r) => r.data),
  digg: (roomId: string, count = '1') => http.post('/live/digg', { room_id: roomId, count }).then((r) => r.data),
  send: (roomId: string, content: string) => http.post('/live/send', { room_id: roomId, content }).then((r) => r.data),
}

// ---------- 私信 ----------
export const msgApi = {
  conversation: (body: any) => http.post('/messages/conversation', body).then((r) => r.data),
  send: (body: any) => http.post('/messages/send', body).then((r) => r.data),
  recvStart: () => http.post('/messages/recv/start').then((r) => r.data),
  recvStop: () => http.post('/messages/recv/stop').then((r) => r.data),
  recvStatus: () => http.get('/messages/recv/status').then((r) => r.data),
}

// ---------- 互动 ----------
export const interactApi = {
  digg: (awemeId: string, diggType = '1') => http.post('/interact/digg', { aweme_id: awemeId, digg_type: diggType }).then((r) => r.data),
  comment: (awemeId: string, content: string, replyId = '') => http.post('/interact/comment', { aweme_id: awemeId, content, reply_id: replyId }).then((r) => r.data),
  collect: (awemeId: string, action = '1') => http.post('/interact/collect', { aweme_id: awemeId, action }).then((r) => r.data),
  collectMove: (awemeId: string, collectName: string, collectId: string) => http.post('/interact/collect/move', { aweme_id: awemeId, collect_name: collectName, collect_id: collectId }).then((r) => r.data),
  collectRemove: (awemeId: string, collectName: string, collectId: string) => http.post('/interact/collect/remove', { aweme_id: awemeId, collect_name: collectName, collect_id: collectId }).then((r) => r.data),
}

// ---------- 任务 ----------
export const tasksApi = {
  list: () => http.get('/tasks').then((r) => r.data),
  get: (id: string) => http.get(`/tasks/${id}`).then((r) => r.data),
  remove: (id: string) => http.delete(`/tasks/${id}`).then((r) => r.data),
  cancel: (id: string) => http.post(`/tasks/${id}/cancel`).then((r) => r.data),
}

// ---------- 下载 ----------
export const downloadsApi = {
  tree: () => http.get('/downloads/tree').then((r) => r.data),
  fileUrl: (path: string) => `/api/downloads/file?path=${encodeURIComponent(path)}`,
}
