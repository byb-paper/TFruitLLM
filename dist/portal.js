const speciesOrder=['pineapple','passionfruit','avocado','sugarapple','guava','rambutan','wampee','dragonfruit','litchi','durian','longan','mango','cashew'];
const sapindaceae=new Set(['litchi','longan','rambutan']);
const grid=document.querySelector('#speciesGrid');
const safe=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let species=[],transcriptomes=[],advanced={};

function renderSpecies(filter='all'){
  const list=species.filter(item=>filter==='all'||(filter==='sapindaceae'?sapindaceae.has(item.key):!sapindaceae.has(item.key)));
  grid.innerHTML=list.map((item,index)=>`<a class="species-card" href="species.html?species=${encodeURIComponent(item.key)}" style="--delay:${index*35}ms"><div class="fruit-image"><img src="assets/species-natural-hd-v5/${encodeURIComponent(item.key)}.jpg" alt="${safe(item.commonName)} fruit growing naturally on the plant"><span>${String(speciesOrder.indexOf(item.key)+1).padStart(2,'0')}</span></div><div class="species-meta"><p>${safe(item.scientificName)}</p><h3>${safe(item.commonName)}</h3><span>OPEN EVIDENCE PROFILE ↗</span></div></a>`).join('');
}

document.querySelector('.species-filter')?.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  document.querySelectorAll('.species-filter button').forEach(item=>item.classList.toggle('active',item===button));renderSpecies(button.dataset.filter);
});

const messages=document.querySelector('#messages'),form=document.querySelector('#chatForm'),input=document.querySelector('#question');
const submitButton=form.querySelector('button');
const conversation=[];
function addMessage(role,text,state=''){
  const element=document.createElement('div');
  element.className=`message ${role}${state?` ${state}`:''}`;
  element.textContent=text;
  messages.appendChild(element);
  messages.scrollTop=messages.scrollHeight;
  return element;
}
async function ask(text){
  const question=text.trim();if(!question||submitButton.disabled)return;
  addMessage('user',question);conversation.push({role:'user',content:question});
  const pending=addMessage('model','TFruitLLM is examining the evidence…','pending');
  input.value='';input.disabled=true;submitButton.disabled=true;
  try{
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:conversation,max_tokens:1024,temperature:.3})});
    const contentType=response.headers.get('content-type')||'';
    if(!contentType.includes('application/json')){
      const body=await response.text();
      const hint=response.status===504
        ? 'TFruitLLM took longer than the Cloud Function time limit to answer.'
        : body.trim().startsWith('<')
          ? 'The EdgeOne /api/chat service returned an HTML error page.'
          : body.slice(0,180);
      throw new Error(`${hint} (HTTP ${response.status})`);
    }
    const result=await response.json();
    if(!response.ok)throw new Error(result.detail||result.error||`Request failed (${response.status})`);
    const rawAnswer=result.choices?.[0]?.message?.content?.trim();
    const answer=rawAnswer?.includes('</think>')
      ? rawAnswer.split('</think>').pop().trim()
      : rawAnswer;
    if(!answer)throw new Error('The model returned an empty response.');
    pending.classList.remove('pending');pending.textContent=answer;
    conversation.push({role:'assistant',content:answer});
  }catch(error){
    pending.classList.remove('pending');pending.classList.add('error');
    pending.textContent=`The research service is temporarily unavailable. ${error.message}`;
    conversation.pop();
  }finally{
    input.disabled=false;submitButton.disabled=false;input.focus();messages.scrollTop=messages.scrollHeight;
  }
}
form.addEventListener('submit',event=>{event.preventDefault();ask(input.value)});
document.querySelector('.prompt-list')?.addEventListener('click',event=>{if(event.target.matches('button'))ask(event.target.textContent)});

Promise.all([fetch('data/genomes.json').then(r=>r.json()),fetch('data/transcriptomes.json').then(r=>r.json()),fetch('data/advanced-omics.json').then(r=>r.json())]).then(([genomes,tx,omics])=>{species=[...genomes.species].sort((a,b)=>speciesOrder.indexOf(a.key)-speciesOrder.indexOf(b.key));transcriptomes=tx.species;advanced=omics.species;renderSpecies()}).catch(()=>grid.innerHTML='<p class="loading">The species atlas is temporarily unavailable.</p>');
