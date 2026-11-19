const messages=document.querySelector('#messages'),form=document.querySelector('#chatForm'),input=document.querySelector('#question');
const submitButton=form.querySelector('button');
const conversation=[];
function normalizeAnswer(text=''){
  return String(text)
    .replace(/(?:^|\s+)Step\s*(\d+)\s*(?:[—–\-:：]\s*)?/gi,(_,number)=>`\n\n${number}. `)
    .replace(/(?:^|\s+)步骤\s*([一二三四五六七八九十\d]+)\s*(?:[—–\-:：]\s*)?/g,(_,number)=>`\n\n${number}. `)
    .replace(/\n{3,}/g,'\n\n')
    .trim();
}
function addMessage(role,text,state=''){
  const element=document.createElement('div');
  element.className=`message ${role}${state?` ${state}`:''}`;
  element.textContent=text;
  messages.appendChild(element);
  messages.scrollTop=messages.scrollHeight;
  return element;
}
function extractErrorMessage(result,status){
  const candidates=[
    result?.detail,
    result?.error?.message,
    result?.error?.detail,
    result?.error,
    result?.message,
  ];
  for(const candidate of candidates){
    if(typeof candidate==='string'&&candidate.trim())return candidate.trim();
    if(candidate&&typeof candidate==='object'){
      try{
        const serialized=JSON.stringify(candidate);
        if(serialized&&serialized!=='{}')return serialized;
      }catch{}
    }
  }
  return `Request failed (${status})`;
}
async function ask(text){
  const question=text.trim();if(!question||submitButton.disabled)return;
  addMessage('user',question);conversation.push({role:'user',content:question});
  const pending=addMessage('model','TropicalfruitLLM 1.0 is examining the evidence…','pending');
  input.value='';input.disabled=true;submitButton.disabled=true;
  try{
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:conversation,max_tokens:1024,temperature:.4})});
    const contentType=response.headers.get('content-type')||'';
    if(!contentType.includes('application/json')){
      const body=await response.text();
      const hint=response.status===504
        ? 'TropicalfruitLLM 1.0 took longer than the Cloud Function time limit to answer.'
        : body.trim().startsWith('<')
          ? 'The EdgeOne /api/chat service returned an HTML error page.'
          : body.slice(0,180);
      throw new Error(`${hint} (HTTP ${response.status})`);
    }
    const result=await response.json();
    if(!response.ok)throw new Error(extractErrorMessage(result,response.status));
    const rawAnswer=result.choices?.[0]?.message?.content?.trim();
    const answer=normalizeAnswer(rawAnswer?.includes('</think>')
      ? rawAnswer.split('</think>').pop().trim()
      : rawAnswer);
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
