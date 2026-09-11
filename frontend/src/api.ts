export type Status = 'queued' | 'running' | 'succeeded' | 'failed' | 'partial'
export type Model = {id: string; name: string; version: string; author: string; description: string; device: string; is_mock: boolean; available: boolean; availability_message: string}
export type Detection = {class_id: number; class_name: string; confidence: number; bbox_xyxy: [number, number, number, number]}
export type Result = {model: Pick<Model, 'id' | 'name' | 'version' | 'author' | 'device'>; is_mock: boolean; status: Status; detections: Detection[]; load_ms: number | null; inference_ms: number | null; error: string | null}
export type UploadedImage = {id: string; width: number; height: number; url: string; filename?: string}
export type Job = {id: string; created_at: string; status: Status; confidence: number; image: UploadedImage; results: Result[]}
export const terminal = (status: Status) => ['succeeded', 'failed', 'partial'].includes(status)
export const labels = ['鼠咬', '毛刺', '缺失孔', '短路', '开路', '杂铜']
export const colors = ['#e86a58', '#d49b22', '#8b6bd6', '#347ddd', '#159d8a', '#c55395']
export const statusLabels: Record<Status, string> = {queued: '等待中', running: '推理中', succeeded: '已完成', failed: '失败', partial: '部分完成'}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败 (${response.status})`)
  }
  return response.status === 204 ? undefined as T : response.json()
}
export function exportUrl(id: string, modelId?: string) {
  return `/api/v1/inferences/${id}/export?format=${modelId ? 'png&model_id='+encodeURIComponent(modelId) : 'json'}`
}
export type Analysis = {enabled: boolean; analysis: string; message?: string | null; error?: string | null}
export async function analyze(imageId: string, detections: Detection[]) {
  return api<Analysis>('/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({image_id: imageId, detections})})
}
