import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp } from 'antd'
import App from './App'

const image={id:'image-1',width:600,height:600,url:'/api/v1/images/image-1',filename:'pcb.png'}
const models=['a','b'].map(id=>({id,name:`模型 ${id.toUpperCase()}`,version:'1.0',author:'Team',description:'示例',device:'cpu',is_mock:true,available:true,availability_message:'模拟演示'}))
const job={id:'job-1',created_at:'2026-09-08T08:00:00Z',status:'succeeded',confidence:.25,image,
  results:models.map((model,i)=>({model,is_mock:true,status:'succeeded',load_ms:0,inference_ms:10,error:null,detections:i?[]:[{class_id:0,class_name:'mouse_bite',confidence:.9,bbox_xyxy:[10,20,30,40]}]}))}
let requests: {url:string;init?:RequestInit}[]=[]
beforeEach(()=>{
  localStorage.clear();requests=[]
  vi.stubGlobal('fetch',vi.fn(async(input:string,init?:RequestInit)=>{
    requests.push({url:input,init})
    let body:unknown
    if(input.endsWith('/health'))body={worker_alive:true}
    else if(input.endsWith('/models'))body=models
    else if(input.endsWith('/images'))body=image
    else if(input.endsWith('/inferences')&&init?.method==='POST')body={id:'job-1',status:'queued'}
    else if(input.includes('/inferences?page='))body={items:[job],total:1}
    else if(input.endsWith('/inferences/job-1'))body=job
    else throw new Error(`Unexpected request: ${input}`)
    return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  }))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
function mount(){
  const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  return render(<QueryClientProvider client={client}><AntApp><App/></AntApp></QueryClientProvider>)
}

test('uploads image, submits two models and displays real contract including empty detections',async()=>{
  const user=userEvent.setup()
  const {container}=mount()
  await screen.findByText('模型 A')
  await user.click(screen.getAllByRole('checkbox')[0])
  await user.click(screen.getAllByRole('checkbox')[1])
  expect(screen.getByText(/已选择模拟模型/)).toBeInTheDocument()
  const file=new File(['fake-image-content'],'pcb.png',{type:'image/png'})
  fireEvent.change(container.querySelector('input[type="file"]')!,{target:{files:[file]}})
  await screen.findByText('图片已就绪')
  await user.click(screen.getByRole('button',{name:/开始检测/}))
  await screen.findByText('未检出缺陷')
  expect(screen.getAllByText('模拟结果')).toHaveLength(2)
  expect(screen.getByText('90.0%')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:/导出 JSON/})).toHaveAttribute('href','/api/v1/inferences/job-1/export?format=json')
  expect(screen.getAllByRole('link',{name:/下载带框图片/})).toHaveLength(2)
  const submission=requests.find(r=>r.init?.method==='POST'&&r.url.endsWith('/inferences'))!
  expect(JSON.parse(submission.init!.body as string)).toEqual({image_id:'image-1',model_ids:['a','b'],confidence:.25})
  expect(container.querySelectorAll('svg[aria-label="缺陷检测框"] rect')).toHaveLength(1)
  await user.click(screen.getByRole('switch'))
  expect(container.querySelectorAll('svg[aria-label="缺陷检测框"]')).toHaveLength(0)
})

test('opens model catalog and history, restores a saved job after remount',async()=>{
  localStorage.setItem('pcb-last-job','job-1')
  const user=userEvent.setup()
  mount()
  await screen.findByText('未检出缺陷')
  await user.click(screen.getByRole('button',{name:/模型目录/}))
  expect(await screen.findByText('团队模型，统一接入')).toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:/检测历史/}))
  await screen.findByText('pcb.png')
  await user.click(screen.getByRole('button',{name:/查\s*看/}))
  await waitFor(()=>expect(screen.getByText('未检出缺陷')).toBeInTheDocument())
})
