'use strict';
const $ = id => document.getElementById(id);
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {config:null, selected:false, module:0, file:null, busy:false, job:null, history:[], uploading:false};
let toastTimer;
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,5500); }
async function api(path, options={}) {
  const response=await fetch('/api/'+path, options);
  if (!response.ok) {
    const result=await response.json().catch(()=>({}));
    throw new Error(typeof result.detail==='string'?result.detail:'请求未完成，请稍后重试。');
  }
  return response.json();
}
const post=(path, body={})=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
const bytes=value=>value<1024**2?(value/1024).toFixed(1)+' KB':(value/1024**2).toFixed(1)+' MB';
const point=(radius,degrees)=>[350+radius*Math.cos(degrees*Math.PI/180),350+radius*Math.sin(degrees*Math.PI/180)];
function sectorPath(outer,inner,start,end) {
  const a=point(outer,start),b=point(outer,end),large=end-start>180?1:0;
  if(!inner)return `M350,350 L${a} A${outer},${outer} 0 ${large} 1 ${b} Z`;
  const c=point(inner,end),d=point(inner,start);
  return `M${a} A${outer},${outer} 0 ${large} 1 ${b} L${c} A${inner},${inner} 0 ${large} 0 ${d} Z`;
}
const modules=[['文档与办公','DOCUMENTS','doc'],['图片与图像','IMAGES','image'],['结构化数据','DATA','data'],['音视频','MEDIA','media'],['解压与破译','ARCHIVES','archive']];
function drawWheel() {
  const hasRing=Boolean(state.file?.targets.length);
  let svg=`<circle cx="350" cy="350" r="290" class="guide-circle"/><circle cx="350" cy="350" r="224" class="guide-circle solid"/><circle cx="350" cy="350" r="180" class="guide-circle solid"/>`;
  modules.forEach(([name,en,symbol],index)=>{
    const start=-126+index*72,end=start+72,mid=start+36;
    const [x,y]=point(114,mid);
    const active=false,available=index<4;
    svg+=`<g role="button" tabindex="0" aria-label="${name}${available?'':'，待开发'}" data-module="${index}"><path d="${sectorPath(180,0,start,end)}" class="wheel-sector ${available?'available'+(active&&state.selected?' selected':''):'future'}"/><svg x="${x-12}" y="${y-35}" width="24" height="24" class="sector-icon ${active?'active-label':''}"><use href="#i-${symbol}"/></svg><text x="${x}" y="${y+10}" text-anchor="middle" class="sector-label ${active?'active-label':''}">${name}</text><text x="${x}" y="${y+27}" text-anchor="middle" class="sector-sub ${active?'active-label':''}">${available?en:'即将开放'}</text></g>`;
  });
  if(hasRing) {
    const targets=state.file.targets,n=targets.length;
    targets.forEach((target,index)=>{
      // SVG full-circle arcs need two halves. A tiny seam handles the single-target ring.
      const start=-90+index*360/n+1,end=-90+(index+1)*360/n-1,mid=(start+end)/2;
      const [x,y]=point(255,mid);
      svg+=`<g class="ring-group${state.busy?' busy':''}" style="animation-delay:${index*.055}s" data-target="${target}" role="button" tabindex="${state.busy?-1:0}" aria-label="转换为 ${target.toUpperCase()}" aria-disabled="${state.busy}"><path d="${sectorPath(291,218,start,end)}" class="ring-segment"/><text x="${x}" y="${y-1}" text-anchor="middle" class="ring-label">${target.toUpperCase()}</text><text x="${x}" y="${y+17}" text-anchor="middle" class="ring-caption">${target==='png'&&state.file.pages>1?'多页打包 ZIP':'点击转换'}</text></g>`;
    });
  }
  $('wheel').innerHTML=svg;
  $('orbit-prompt').style.opacity=hasRing||state.selected?'0':'1';
  $('ring-legend').hidden=!hasRing;
  document.querySelectorAll('[data-module]').forEach(el=>bindActivate(el,()=>selectModule(Number(el.dataset.module))));
  document.querySelectorAll('[data-target]').forEach(el=>bindActivate(el,()=>startConversion(el.dataset.target)));
}
function bindActivate(element,callback) { element.addEventListener('click',callback);element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();callback();}}); }
function step(number) {
  for(let n=1;n<=3;n++) $('step-'+n).classList.toggle('current',n===number);
  $('workspace-step').textContent=['01 / 选择板块','02 / 添加文件','03 / 选择目标格式'][number-1];
}
function selectModule(index, pick=true) {
  if(index>3){toast('解压与破译已在桌面挂件中开放，请通过启动工具.cmd使用。');return;}
  if(state.busy||state.uploading){toast('当前文件正在处理，请稍候。');return;}
  state.selected=true;state.module=index;
  $('empty-detail').hidden=true;$('file-detail').hidden=false;
  $('detail-step').textContent='02';$('detail-title').textContent=modules[index][0];
  $('hub-title').textContent=modules[index][0];$('hub-subtitle').textContent=state.file?'在外环选择格式':'添加文件，展开可能';
  document.querySelector('.accepted').textContent=['DOC / DOCX · PDF · XLS / XLSX · PPT / PPTX · MD · HTML · CSV · TXT · EPUB','JPG · PNG · TIFF · WebP · HEIC · AVIF · RAW · SVG · GIF','JSON · YAML / YML · XML · CSV / TSV · JSONL','MP4 · WebM · MKV · MOV · WAV · FLAC · MP3 · M4A · AAC'][index];
  $('upload-button').querySelector('span:last-child').textContent='单个文件最大 '+(index===3?'2 GB':'500 MB');
  step(state.file?3:2);drawWheel();
  if(pick)$('file-input').click();
}
function renderFile() {
  const file=state.file;
  $('file-info').hidden=!file;
  if(!file)return;
  $('file-ext').textContent=file.ext.toUpperCase();$('file-name').textContent=file.name;$('file-name').title=file.name;
  $('file-size').textContent=bytes(file.size)+(file.pages?' · '+file.pages+' 页':'');
  $('target-count').textContent=file.targets.length;
  $('target-chips').innerHTML=file.targets.map(t=>`<button class="target-chip" data-chip="${t}" title="${esc(state.config.notes[file.ext+':'+t]||'点击开始转换')}">${t.toUpperCase()}</button>`).join('');
  document.querySelectorAll('[data-chip]').forEach(el=>el.onclick=()=>startConversion(el.dataset.chip));
  let options='';
  if(file.ext==='pdf')options=`<label title="仅在页面文字不足时使用 OCR">扫描页自动 OCR <input id="ocr-option" type="checkbox" checked></label><label>PNG 清晰度<select id="dpi-option"><option value="96">96 DPI · 较小</option><option value="150" selected>150 DPI · 标准</option><option value="200">200 DPI · 清晰</option><option value="300">300 DPI · 高清</option></select></label>`;
  if(['xls','xlsx'].includes(file.ext))options=`<label>导出工作表<select id="sheet-option">${file.sheets.map(s=>`<option>${esc(s)}</option>`).join('')}</select></label>`;
  if(['json','xml'].includes(file.ext))options='<label>XML 根名称<input id="xml-root" value="root"></label><label>XML 映射<select id="xml-mode"><option value="preserve">属性 @ / 文本 #text</option><option value="elements">仅元素</option></select></label><label>CSV 记录路径<input id="records-path" placeholder="如 data.items"></label><label>嵌套字段<select id="nested-csv"><option value="json">JSON 文本</option><option value="reject">拒绝嵌套</option></select></label>';
  if(file.ext==='mp4')options='<label>GIF 起始秒<input id="clip-start" type="number" min="0" value="0"></label><label>GIF 时长<input id="clip-duration" type="number" min="0.1" max="30" value="5"></label><label>GIF 帧率<input id="gif-fps" type="number" min="1" max="30" value="12"></label><label>GIF 宽度<input id="gif-width" type="number" min="64" max="1280" value="480"></label>';
  $('file-options').innerHTML=options;
  $('target-hint').textContent=file.targets.length?'点击圆盘外环的格式，立即开始转换。':'示意图中 '+file.ext.toUpperCase()+' 仅为输出格式，暂无后续转换方向。请更换文件。';
  $('hub-subtitle').textContent=file.targets.length?'在外环选择格式':'此格式暂无转换方向';
  $('detail-step').textContent='03';step(3);drawWheel();
}
async function uploadFile(file) {
  if(!file)return;
  if(state.busy||state.uploading){toast('请等待当前文件处理结束。');return;}
  if(!file.size){toast('不能添加空文件。');return;}
  const originalExt=file.name.split('.').pop().toLowerCase();
  const ext=state.config.aliases?.[originalExt]||originalExt;
  if(!state.config.graph[ext]?.length){toast('文件不符合转化格式要求。');return;}
  const module=state.config.modules[ext]||0,limit=state.config.limitsMB[module]*1024**2;
  if(file.size>limit){toast('单个文件不能超过 '+(module===3?'2 GB':'500 MB')+'。');return;}
  state.uploading=true;
  const button=$('upload-button');button.disabled=true;button.querySelector('strong').textContent='正在读取文件…';
  try {
    const data=new FormData();data.append('file',file);
    const uploaded=await api('files',{method:'POST',body:data});
    state.uploading=false;selectModule(state.config.modules[uploaded.ext]||0,false);state.uploading=true;
    const previous=state.file;
    state.file=uploaded;state.job=null;$('job-detail').hidden=true;renderFile();
    if(previous)await api('files/'+previous.id,{method:'DELETE'}).catch(()=>{});
    toast(uploaded.targets.length?`已识别 ${uploaded.ext.toUpperCase()} · 外环已展开 ${uploaded.targets.length} 种目标格式`:'此文件类型在示意图中仅为输出，请选择其他文档。');
  } catch(error){toast(error.message);}
  finally{state.uploading=false;button.disabled=false;button.querySelector('strong').textContent='点击选择或拖入文件';$('file-input').value='';}
}
async function startConversion(target) {
  if(!state.file||state.busy||state.uploading)return;
  const options={ocr:$('ocr-option')?.checked??true,dpi:Number($('dpi-option')?.value||150),sheet:$('sheet-option')?.value||null};
  Object.assign(options,{xml_root:$('xml-root')?.value||'root',xml_mode:$('xml-mode')?.value||'preserve',records_path:$('records-path')?.value||'',nested_csv:$('nested-csv')?.value||'json',clip_start:Number($('clip-start')?.value||0),clip_duration:Number($('clip-duration')?.value||5),gif_fps:Number($('gif-fps')?.value||12),gif_width:Number($('gif-width')?.value||480)});
  state.busy=true;drawWheel();setControls(true);
  const note=state.config.notes[state.file.ext+':'+target];
  if(note)$('target-hint').textContent=note;
  try {
    state.job=await post('jobs',{fileId:state.file.id,target,options});
    renderJob();
    while(['running','queued'].includes(state.job.status)) {
      await new Promise(resolve=>setTimeout(resolve,700));
      state.job=await api('jobs/'+state.job.id);renderJob();
    }
    if(state.job.status==='done'){
      const job=state.job;
      $('recent-strip').hidden=false;$('recent-name').textContent=job.outputName;
      $('recent-route').textContent=state.file.ext.toUpperCase()+' → '+target.toUpperCase();
      $('recent-download').href='/api/download/'+job.id;
      toast('转换完成，结果已保存在本地。');
    }
    await loadHistory();
  } catch(error){toast(error.message);if(state.job){state.job.status='error';state.job.message=error.message;renderJob();}}
  finally{state.busy=false;setControls(false);drawWheel();}
}
function setControls(busy) { $('upload-button').disabled=busy;$('remove-file').disabled=busy;document.querySelectorAll('.target-chip,.file-options input,.file-options select').forEach(el=>el.disabled=busy); }
function renderJob() {
  const job=state.job;if(!job)return;
  const done=job.status==='done',error=job.status==='error';
  $('job-detail').hidden=false;
  $('job-detail').innerHTML=`<div class="job-box${error?' error-box':''}"><div class="job-state${error?' error-state':''}">${done?icon('check'):error?'!':'<span class="spinner"></span>'}${done?'转换完成':error?'转换未完成':'正在转换'}</div><div class="job-route">${esc(state.file.ext.toUpperCase())}${icon('arrow')}${esc(job.target.toUpperCase())}</div>${done?`<div class="job-message">${esc(job.outputName)} · ${bytes(job.size)}</div><a class="primary-button" href="/api/download/${job.id}">${icon('down')}保存文件</a><button class="secondary-button open-output">${icon('folder')}打开结果文件夹</button>`:`<div class="job-message">${esc(job.message)}</div>${error?`<button class="secondary-button" id="retry-button">重新转换</button>`:`<div class="progress-track"><div class="progress-fill" style="width:${job.progress}%"></div></div>`}`}${job.warnings?.length?`<p class="job-warning">${job.warnings.map(esc).join('<br>')}</p>`:''}</div>`;
  bindOpenOutput();if($('retry-button'))$('retry-button').onclick=()=>startConversion(job.target);
}
function bindOpenOutput(){document.querySelectorAll('.open-output').forEach(button=>button.onclick=()=>post('open-output').catch(error=>toast(error.message)));}
async function loadHistory() {
  state.history=await api('jobs');
  $('history-count').textContent=state.history.length;
  $('history-list').innerHTML=state.history.length?state.history.map(job=>`<div class="history-row"><span class="file-ext">${esc(job.target.toUpperCase())}</span><div class="history-info"><strong>${esc(job.sourceName)} → ${esc(job.target.toUpperCase())}</strong><small>${esc(new Date(job.createdAt).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}))} · ${esc(job.message)}</small></div>${job.status==='done'?`<a href="/api/download/${job.id}" aria-label="保存 ${esc(job.outputName)}">${icon('down')}</a>`:`<span>${job.status==='error'?'未完成':'处理中'}</span>`}</div>`).join(''):'<div class="history-empty">还没有转换记录。从一个文件开始吧。</div>';
}
function showView(history) {
  $('convert-view').hidden=history;$('history-view').hidden=!history;
  $('nav-history').classList.toggle('active',history);$('nav-convert').classList.toggle('active',!history);
  $('page-name').textContent=history?'转换记录':'文件转换';
  if(history)loadHistory().catch(error=>toast(error.message));
}
$('nav-convert').onclick=()=>showView(false);$('nav-history').onclick=()=>showView(true);
$('start-button').onclick=()=>selectModule(0);$('upload-button').onclick=()=>$('file-input').click();
$('file-input').onchange=()=>uploadFile($('file-input').files[0]);
$('remove-file').onclick=async()=>{
  if(state.busy)return;
  try{await api('files/'+state.file.id,{method:'DELETE'});state.file=null;state.job=null;$('job-detail').hidden=true;$('file-info').hidden=true;$('hub-subtitle').textContent='添加文件，展开可能';$('detail-step').textContent='02';step(2);drawWheel();}catch(error){toast(error.message);}
};
let dragDepth=0;
document.addEventListener('dragover',event=>{event.preventDefault();});
document.addEventListener('drop',event=>{event.preventDefault();dragDepth=0;$('drop-area').classList.remove('dragging');if(event.dataTransfer.files.length>1){toast('当前每次转换一个文件，请逐个添加。');return;}uploadFile(event.dataTransfer.files[0]);});
$('drop-area').addEventListener('dragenter',event=>{event.preventDefault();dragDepth++;$('drop-area').classList.add('dragging');});
$('drop-area').addEventListener('dragleave',()=>{dragDepth--;if(dragDepth<=0)$('drop-area').classList.remove('dragging');});
$('help-button').onclick=()=>$('help-dialog').showModal();document.querySelectorAll('.dialog-close').forEach(el=>el.onclick=()=>$('help-dialog').close());
$('help-dialog').addEventListener('click',event=>{if(event.target===$('help-dialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
$('exit-button').onclick=async()=>{try{await post('shutdown');$('exit-button').textContent='已退出';toast('工具已退出，可以关闭此窗口。');document.querySelectorAll('button').forEach(el=>el.disabled=true);}catch(error){toast(error.message);}};
bindOpenOutput();step(1);drawWheel();
(async()=>{try{state.config=await api('config');const missing=Object.entries(state.config.engines).filter(([,ok])=>!ok).map(([name])=>name);if(missing.length)toast('转换引擎未齐全：'+missing.join('、')+'。请使用完整便携版。');await loadHistory();}catch(error){toast(error.message);$('start-button').disabled=true;}})();
