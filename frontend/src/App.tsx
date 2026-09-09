import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App as AntApp, Button, Card, Checkbox, Empty, Progress, Select, Slider, Space, Spin, Switch, Table, Tag, Upload, Popconfirm } from 'antd'
import { AppstoreOutlined, ArrowRightOutlined, CheckCircleOutlined, CloudUploadOutlined, DownloadOutlined, ExperimentOutlined, HistoryOutlined, ScanOutlined } from '@ant-design/icons'
import { api, analyze, colors, exportUrl, labels, statusLabels, terminal } from './api'
import type { Job, Model, Result, UploadedImage } from './api'

function ImageCanvas({image, result, showBoxes = true}: {image: UploadedImage; result?: Result; showBoxes?: boolean}) {
  const [zoom, setZoom] = useState(100)
  return <><div className="image-toolbar"><span>{image.width} × {image.height} px</span><Space><span>缩放</span><Select aria-label="图片缩放" size="small" value={zoom} onChange={setZoom} options={[100, 150, 200, 300].map(v => ({value:v, label:`${v}%`}))}/></Space></div>
    <div className="image-viewport"><div className="image-stage" style={{width:`${zoom}%`}}>
      <img src={image.url} alt="PCB 检测原图"/>
      {showBoxes && result && <svg viewBox={`0 0 ${image.width} ${image.height}`} aria-label="缺陷检测框">
        {result.detections.map((d, i) => {const [x1,y1,x2,y2] = d.bbox_xyxy; const font = Math.max(10, image.width/48)
          return <g key={i}><rect x={x1} y={y1} width={x2-x1} height={y2-y1} fill="none" stroke={colors[d.class_id]} strokeWidth={Math.max(2,image.width/300)}/><text x={x1} y={Math.max(font,y1-4)} fill={colors[d.class_id]} stroke="#fff" strokeWidth={font/12} paintOrder="stroke" fontWeight="600" fontSize={font}>{labels[d.class_id]} {(d.confidence*100).toFixed(0)}%</text></g>})}
      </svg>}
    </div></div></>
}

function ResultCard({job, result, showBoxes}: {job: Job; result: Result; showBoxes: boolean}) {
  const done = result.status === 'succeeded'
  const [analysis, setAnalysis] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const {message} = AntApp.useApp()
  const runAnalysis = async () => {
    setAnalyzing(true)
    try {
      const res = await analyze(job.image.id, result.detections)
      if (res.error) { message.error(res.error); setAnalysis(res.analysis || null) }
      else if (!res.enabled) { message.warning(res.message || 'AI 分析不可用'); setAnalysis(null) }
      else setAnalysis(res.analysis)
    } catch (e) { message.error((e as Error).message) }
    finally { setAnalyzing(false) }
  }
  return <Card className="result-card" title={<Space>{result.model.name}{result.is_mock && <Tag color="gold">模拟结果</Tag>}</Space>} extra={<Tag color={done ? 'green' : result.status==='failed' ? 'red' : 'blue'}>{statusLabels[result.status]}</Tag>}>
    <div className="result-meta"><span>{result.model.version} · {result.model.device.toUpperCase()}</span><span>{result.model.author}</span></div>
    <ImageCanvas image={job.image} result={result} showBoxes={showBoxes}/>
    {result.error && <Alert type="error" message={result.error} showIcon/>}
    {!terminal(result.status) && <div className="waiting"><Spin size="small"/> {result.status === 'queued' ? '等待串行执行' : '模型正在推理…'}</div>}
    {done && <><div className="result-stats"><div><strong>{result.detections.length}</strong><span>检出缺陷</span></div><div><strong>{result.inference_ms?.toFixed(1)}<small> ms</small></strong><span>推理耗时</span></div><div><strong>{result.load_ms?.toFixed(1)}<small> ms</small></strong><span>加载耗时</span></div></div>
      <div className="class-summary">{labels.map((name, id) => <Tag key={name} color={colors[id]}>{name} {result.detections.filter(d => d.class_id===id).length}</Tag>)}</div>
      {result.detections.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未检出缺陷"/> : <Table size="small" pagination={false} rowKey="key" dataSource={result.detections.map((d,i)=>({...d,key:i}))} columns={[
        {title:'缺陷类别', dataIndex:'class_id', render: (id:number)=><span><i className="class-dot" style={{background:colors[id]}}/>{labels[id]}</span>},
        {title:'置信度', dataIndex:'confidence', render:(c:number)=>`${(c*100).toFixed(1)}%`},
        {title:'坐标 (xyxy)', dataIndex:'bbox_xyxy', render:(box:number[]) => <span className="coordinates">{box.map(Math.round).join(', ')}</span>},
      ]}/>}
      <Button className="export-button" icon={<DownloadOutlined/>} href={exportUrl(job.id,result.model.id)} disabled={!terminal(job.status)}>下载带框图片</Button>
      {!result.is_mock && <Button className="analyze-button" icon={<ExperimentOutlined/>} loading={analyzing} onClick={runAnalysis}>AI 分析缺陷</Button>}
      {analysis && <div className="ai-analysis"><h4>AI 分析结果</h4><p style={{whiteSpace:'pre-wrap'}}>{analysis}</p></div>}
    </>}
  </Card>
}

function JobResults({job}: {job: Job}) {
  const [showBoxes, setShowBoxes] = useState(true)
  const finished = job.results.filter(r=>terminal(r.status)).length
  return <section className="results"><div className="section-heading"><div><h2>检测结果 <Tag>{statusLabels[job.status]}</Tag></h2><p>同一原图 · 阈值 {job.confidence.toFixed(2)} · {new Date(job.created_at).toLocaleString()}</p></div><Space><Switch checked={showBoxes} onChange={setShowBoxes} size="small"/>显示检测框<Button icon={<DownloadOutlined/>} href={exportUrl(job.id)} disabled={!terminal(job.status)}>导出 JSON</Button></Space></div>
    {!terminal(job.status) && <Progress percent={Math.round(finished/job.results.length*100)} status="active"/>}
    <div className="results-grid">{job.results.map(r=><ResultCard key={r.model.id} job={job} result={r} showBoxes={showBoxes}/>)}</div>
    <p className="footnote">推理耗时包含预处理、模型推理及后处理；加载耗时单独记录，缓存命中时为 0。此处耗时不作为严格性能基准。未检出缺陷不等同于产品合格。</p>
  </section>
}

export default function App() {
  const [page,setPage] = useState('workbench')
  const [selected,setSelected] = useState<string[]>([])
  const [image,setImage] = useState<UploadedImage | null>(null)
  const [confidence,setConfidence] = useState(.25)
  const [jobId,setJobId] = useState<string | null>(()=>localStorage.getItem('pcb-last-job'))
  const [historyPage,setHistoryPage] = useState(1)
  const {message} = AntApp.useApp()
  const client = useQueryClient()
  const models = useQuery({queryKey:['models'],queryFn:()=>api<Model[]>('/models')})
  const health = useQuery({queryKey:['health'],queryFn:()=>api<{worker_alive:boolean}>('/health'),refetchInterval:10000})
  const job = useQuery({queryKey:['job',jobId], queryFn:()=>api<Job>(`/inferences/${jobId}`),enabled:!!jobId,
    refetchInterval:q=>q.state.data && terminal(q.state.data.status) ? false : q.state.error ? false : 1000})
  const history = useQuery({queryKey:['history',historyPage],queryFn:()=>api<{items:Job[];total:number}>(`/inferences?page=${historyPage}`),enabled:page==='history',refetchInterval:page==='history'?3000:false})
  useEffect(()=>{if(jobId)localStorage.setItem('pcb-last-job',jobId);else localStorage.removeItem('pcb-last-job')},[jobId])
  const upload = useMutation({mutationFn:async(file:File)=>{const data=new FormData();data.append('file',file);return api<UploadedImage>('/images',{method:'POST',body:data})},
    onSuccess:(data)=>{setImage(data);setJobId(null);message.success('图片已上传')},onError:(e:Error)=>message.error(e.message)})
  const submit = useMutation({mutationFn:()=>api<{id:string}>('/inferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_id:image?.id,model_ids:selected,confidence})}),
    onSuccess:data=>{setJobId(data.id);client.invalidateQueries({queryKey:['history']})},onError:(e:Error)=>message.error(e.message)})
  const remove = useMutation({mutationFn:(id:string)=>api<void>(`/inferences/${id}`,{method:'DELETE'}),onSuccess:(_,id)=>{if(jobId===id)setJobId(null);setImage(null);client.invalidateQueries({queryKey:['history']});message.success('记录已删除')},onError:(e:Error)=>message.error(e.message)})
  const active = !!job.data && !terminal(job.data.status)
  const nav = [{id:'workbench',label:'检测工作台',icon:<ScanOutlined/>},{id:'models',label:'模型目录',icon:<AppstoreOutlined/>},{id:'history',label:'检测历史',icon:<HistoryOutlined/>}]
  return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brand-icon"><ScanOutlined/></div><div>PCB <b>Insight</b><small>电路板缺陷检测平台</small></div></div><div className="nav-label">工作空间</div><nav>{nav.map(item=><button key={item.id} className={page===item.id?'active':''} onClick={()=>setPage(item.id)}>{item.icon}{item.label}{page===item.id && <span className="nav-dot"/>}</button>)}</nav><div className="sidebar-bottom"><div className="team-symbol"><ExperimentOutlined/></div><strong>让模型成果清晰可见</strong><p>统一推理协议<br/>连接团队的每一个模型</p><span>LOCAL WORKSPACE · V1.0</span></div></aside>
    <div className="main"><header><span>工作空间 <span className="slash">/</span> {nav.find(n=>n.id===page)?.label}</span><Space><span className={`status-dot ${health.data?.worker_alive?'online':''}`}/>{health.data?.worker_alive?'服务已连接':'服务连接中断'}<span className="avatar">PCB</span></Space></header>
      <main><div className="page-heading"><div><div className="eyebrow">PCB DEFECT INSPECTION</div><h1>{page==='workbench'?'从一张图片，洞察每一处缺陷':page==='models'?'团队模型，统一接入': '每一次检测，都有迹可循'}</h1><p>{page==='workbench'?'上传电路板图片，选择模型，直观比较不同模型的检测结果。':page==='models'?'查看模型版本与运行状态，通过适配器连接不同成员的训练成果。':'回看检测结果，追溯模型版本，导出可分享的记录。'}</p></div><Tag className="workspace-tag">团队演示工作区</Tag></div>
      {health.isError && <Alert type="error" showIcon message="无法连接后端，请确认 FastAPI 已在 8000 端口启动。"/>}
      {models.isError && <Alert type="error" message={models.error.message} action={<Button onClick={()=>models.refetch()}>重试</Button>}/>}
      {page==='workbench' && <><div className="workflow"><span><b>01</b> 上传图片</span><ArrowRightOutlined/><span><b>02</b> 选择模型</span><ArrowRightOutlined/><span><b>03</b> 查看与对比</span></div><div className="input-grid"><Card title={<><span className="step-number">01</span> 检测图片</>} extra={<span className="muted">JPEG / PNG</span>}>
        <Upload.Dragger accept="image/jpeg,image/png" showUploadList={false} disabled={upload.isPending || active} beforeUpload={file=>{if(file.size>10*1024*1024){message.error('图片不能超过 10 MB');return false}upload.mutate(file);return false}}>
          {upload.isPending?<Spin/>:<><CloudUploadOutlined className="upload-icon"/><h3>拖拽图片到此处，或点击上传</h3><p>最大 10 MB · 不超过 2500 万像素</p></>}
        </Upload.Dragger>
        {image && <div className="upload-preview"><img src={image.url} alt="已上传图片缩略图"/><div><strong><CheckCircleOutlined/> 图片已就绪</strong><p>{image.width} × {image.height} px</p></div><Button type="text" onClick={()=>setImage(null)} disabled={active}>移除</Button></div>}
        <div className="upload-note">建议上传清晰的电路板图片，保留原始细节以观察微小缺陷。</div>
      </Card><Card title={<><span className="step-number">02</span> 推理配置</>}><div className="field-label">选择模型 <span>可多选，按顺序执行</span></div><div className="model-options">{models.isLoading?<Spin/>:models.data?.map(m=><label className={`model-option ${selected.includes(m.id)?'selected':''}`} key={m.id}><Checkbox checked={selected.includes(m.id)} disabled={!m.available || active} onChange={e=>setSelected(e.target.checked?[...selected,m.id]:selected.filter(id=>id!==m.id))}/><div><strong>{m.name}</strong><small>{m.version} · {m.device.toUpperCase()}{!m.available?` · ${m.availability_message}`:''}</small></div><Tag color={m.is_mock?'gold':'cyan'}>{m.is_mock?'模拟':'真实模型'}</Tag></label>)}</div><div className="field-label threshold">置信度阈值 <strong>{confidence.toFixed(2)}</strong></div><Slider aria-label="置信度阈值" value={confidence} min={0} max={1} step={.01} onChange={setConfidence} disabled={active}/><Button block size="large" type="primary" icon={<ScanOutlined/>} loading={submit.isPending || active} disabled={!image || !selected.length || upload.isPending} onClick={()=>submit.mutate()}>开始检测{selected.length?` · ${selected.length} 个模型`:''}</Button></Card></div>
      {selected.some(id=>models.data?.find(m=>m.id===id)?.is_mock) && <Alert className="demo-alert" type="warning" showIcon message="已选择模拟模型：结果仅用于系统演示，不代表真实缺陷或模型准确率。"/>}
      {job.isError && <Alert type="error" message={job.error.message} action={<Button onClick={()=>setJobId(null)}>关闭记录</Button>}/>}
      {jobId && job.isLoading && <div className="loading"><Spin/></div>}
      {job.data?<JobResults job={job.data}/>:!jobId && <div className="empty-results"><ScanOutlined/><h3>检测结果将在这里呈现</h3><p>完成图片上传并选择模型，即可开始第一次检测。</p></div>}</>}
      {page==='models' && <div className="catalog-grid">{models.data?.map(m=><Card key={m.id} title={<Space><ExperimentOutlined/>{m.name}</Space>} extra={<Tag color={m.available?'green':'default'}>{m.available?'可用':'未就绪'}</Tag>}><div className="catalog-description">{m.description}</div><dl><dt>模型版本</dt><dd>{m.version}</dd><dt>贡献成员</dt><dd>{m.author}</dd><dt>运行设备</dt><dd>{m.device}</dd><dt>结果类型</dt><dd>{m.is_mock?'模拟结果':'真实推理'}</dd></dl><Alert type={m.is_mock?'warning':'info'} message={m.availability_message}/></Card>)}</div>}
      {page==='history' && <Card title="检测记录" extra={<Button onClick={()=>history.refetch()}>刷新</Button>}>{history.isError && <Alert type="error" message={history.error.message}/>}<Table rowKey="id" loading={history.isLoading} dataSource={history.data?.items} scroll={{x:850}} pagination={{current:historyPage,total:history.data?.total,pageSize:10,showSizeChanger:false,onChange:setHistoryPage}} columns={[
        {title:'检测图片',render:(_,j:Job)=><div className="history-image"><img src={j.image.url} alt="历史图片"/><span>{j.image.filename}</span></div>},
        {title:'检测时间',dataIndex:'created_at',render:(date:string)=>new Date(date).toLocaleString()},
        {title:'模型',render:(_,j:Job)=><Space wrap>{j.results.map(r=><Tag key={r.model.id} color={r.is_mock?'gold':'cyan'}>{r.model.name}{r.is_mock?' · 模拟':''}</Tag>)}</Space>},
        {title:'状态',dataIndex:'status',render:(status:Job['status'])=>statusLabels[status]},
        {title:'操作',render:(_,j:Job)=><Space><Button size="small" onClick={()=>{setJobId(j.id);setPage('workbench');setImage(j.image);setConfidence(j.confidence);setSelected(j.results.map(r=>r.model.id).filter(id=>models.data?.some(m=>m.id===id&&m.available)))}}>查看</Button><Popconfirm title="删除该记录及无引用图片？" onConfirm={()=>remove.mutate(j.id)}><Button size="small" danger disabled={!terminal(j.status)} loading={remove.isPending && remove.variables===j.id}>删除</Button></Popconfirm></Space>},
      ]}/></Card>}
      <footer>PCB Insight <span>统一协议 · 多模型对比 · 本地记录</span></footer></main>
    </div></div>
}
