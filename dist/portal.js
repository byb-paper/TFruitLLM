const speciesOrder=['pineapple','passionfruit','avocado','sugarapple','guava','rambutan','wampee','dragonfruit','litchi','durian','longan','mango','cashew'];
const sapindaceae=new Set(['litchi','longan','rambutan']);
const grid=document.querySelector('#speciesGrid');
const safe=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let species=[],transcriptomes=[],advanced={};

function renderSpecies(filter='all'){
  const list=species.filter(item=>filter==='all'||(filter==='sapindaceae'?sapindaceae.has(item.key):!sapindaceae.has(item.key)));
  grid.innerHTML=list.map((item,index)=>`<a class="species-card" href="species.html?species=${encodeURIComponent(item.key)}" style="--delay:${index*35}ms"><div class="fruit-image"><img src="assets/species-natural-hd-v5/${encodeURIComponent(item.key)}.jpg" alt="${safe(item.commonName)} fruit growing naturally on the plant"><span>${String(speciesOrder.indexOf(item.key)+1).padStart(2,'0')}</span></div><div class="species-meta"><p>${safe(item.scientificName)}</p><h3>${safe(item.commonName)}</h3><span>OPEN EVIDENCE PROFILE ↗</span></div></a>`).join('');
}

document.querySelector('.species-filter').addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  document.querySelectorAll('.species-filter button').forEach(item=>item.classList.toggle('active',item===button));renderSpecies(button.dataset.filter);
});

function findSpecies(question){const q=question.toLowerCase();return species.find(item=>q.includes(item.key)||q.includes(item.commonName.toLowerCase())||q.includes(item.scientificName.toLowerCase()))}
function answer(question){
  const q=question.toLowerCase();
  if(q.includes('thirteen')||q.includes('13')||q.includes('which species')||q.includes('integrated'))return `The atlas integrates ${species.map(item=>item.commonName).join(', ')}.`;
  const item=findSpecies(question);if(!item)return 'Please name a species such as litchi, longan, mango, durian or pineapple so I can guide you to its evidence profile.';
  const tx=transcriptomes.find(row=>row.scientificName===item.scientificName||row.commonName?.toLowerCase()===item.commonName.toLowerCase());
  const records=advanced[item.key]||[];const types=[...new Set(records.map(row=>row.omicsType).filter(Boolean))];
  if(/stress|disease|abiotic|biotic/.test(q))return `${item.commonName} has a Stress Response route in its species profile. Open the profile to view available abiotic, biotic or disease-related evidence by omics modality.`;
  if(/development|growth|fruit|tissue/.test(q))return `${item.commonName} has a Growth & Development route linking developmental and tissue evidence to the available sequencing modalities.`;
  if(/transcript|rna/.test(q))return tx||types.some(type=>/rna|transcript/i.test(type))?`${item.commonName} includes transcriptome evidence. Open its profile, choose a biological theme, and continue to the omics view for curated research accessions.`:`No curated transcriptome list is currently presented for ${item.commonName}.`;
  return `${item.commonName} has an integrated genome profile${types.length?` connected with ${types.join(', ')}`:''}. Open the species card to explore evidence by biological theme.`;
}

const messages=document.querySelector('#messages'),form=document.querySelector('#chatForm'),input=document.querySelector('#question');
function ask(text){if(!text.trim())return;messages.insertAdjacentHTML('beforeend',`<div class="message user">${safe(text)}</div><div class="message model">${safe(answer(text))}</div>`);messages.scrollTop=messages.scrollHeight;input.value=''}
form.addEventListener('submit',event=>{event.preventDefault();ask(input.value)});
document.querySelector('.prompt-list').addEventListener('click',event=>{if(event.target.matches('button'))ask(event.target.textContent)});

Promise.all([fetch('data/genomes.json').then(r=>r.json()),fetch('data/transcriptomes.json').then(r=>r.json()),fetch('data/advanced-omics.json').then(r=>r.json())]).then(([genomes,tx,omics])=>{species=[...genomes.species].sort((a,b)=>speciesOrder.indexOf(a.key)-speciesOrder.indexOf(b.key));transcriptomes=tx.species;advanced=omics.species;renderSpecies()}).catch(()=>grid.innerHTML='<p class="loading">The species atlas is temporarily unavailable.</p>');
