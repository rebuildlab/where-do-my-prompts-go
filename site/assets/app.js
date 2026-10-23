(function(){
  'use strict';
  var root=document.documentElement;
  // Theme: dark by default, light if chosen (saved in localStorage)
  var tb=document.getElementById('theme');
  function syncTheme(){if(!tb)return;var to=root.getAttribute('data-theme')==='light'?'Dark':'Light';
    tb.setAttribute('aria-label',to+' theme');tb.firstChild.nodeValue=to;}
  if(tb){syncTheme();tb.addEventListener('click',function(){
    var light=root.getAttribute('data-theme')!=='light';
    if(light)root.setAttribute('data-theme','light');else root.removeAttribute('data-theme');
    try{localStorage.setItem('theme',light?'light':'dark');}catch(_){}
    syncTheme();
  });}

  // Copy-citation buttons (tool pages)
  document.addEventListener('click',function(ev){
    var b=ev.target.closest&&ev.target.closest('button.copy');
    if(!b)return;
    var txt=b.getAttribute('data-cite'),old=b.textContent;
    function done(ok){b.textContent=ok?'Copied':'Copy failed';setTimeout(function(){b.textContent=old;},1600);}
    if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(function(){done(true);},function(){done(false);});}
    else{var t=document.createElement('textarea');t.value=txt;document.body.appendChild(t);t.select();
      try{done(document.execCommand('copy'));}catch(e){done(false);}document.body.removeChild(t);}
  });

  // Event-stream severity filters
  [].forEach.call(document.querySelectorAll('.logbar'),function(bar){
    var log=bar.parentNode.querySelector('.log');if(!log)return;
    bar.addEventListener('click',function(ev){
      var b=ev.target.closest('button');if(!b)return;
      var sev=b.getAttribute('data-sev');
      [].forEach.call(bar.querySelectorAll('button'),function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});
      [].forEach.call(log.children,function(li){li.hidden=!!sev&&li.getAttribute('data-sev')!==sev;});
    });
  });

  var table=document.getElementById('t');
  if(!table)return;
  var $=function(id){return document.getElementById(id);};
  var q=$('q'),cat=$('f-cat'),tr=$('f-trains'),z=$('f-zdr'),rg=$('f-region'),baa=$('f-baa'),cnt=$('count'),none=$('none'),parsed=$('qparsed');
  var tbody=table.tBodies[0],rows=[].slice.call(tbody.rows);
  var state={text:'',vendor:''};
  var sels={cat:cat,trains:tr,zdr:z,region:rg};
  var ALIAS={category:'cat',vendor:'vendor',tool:'vendor',cat:'cat',trains:'trains',zdr:'zdr',region:'region',baa:'baa'};
  function opts(sel){return [].slice.call(sel.options).map(function(o){return o.value;}).filter(Boolean);}
  function norm(key,val){
    val=val.toLowerCase().replace(/-/g,' ');
    if(key==='zdr'&&(val==='na'||val==='n a'))val='n/a';
    var o=opts(sels[key]);
    for(var i=0;i<o.length;i++){if(o[i].toLowerCase()===val)return o[i];}
    if(key==='cat'){for(var j=0;j<o.length;j++){if(o[j].toLowerCase().indexOf(val)===0)return o[j];}}
    return null;
  }
  function tokens(s){var m=s.match(/(\S+?:"[^"]*"|"[^"]*"|\S+)/g);return m||[];}
  function parse(){
    var bad=[],words=[];
    state.vendor='';
    Object.keys(sels).forEach(function(k){sels[k].value='';});
    baa.checked=false;
    tokens(q.value).forEach(function(t){
      var i=t.indexOf(':'),key=i>0?ALIAS[t.slice(0,i).toLowerCase()]:null,val=i>0?t.slice(i+1).replace(/^"|"$/g,''):'';
      if(i>0&&!key){bad.push(t+' (unknown key)');return;}
      if(!key){words.push(t.replace(/^"|"$/g,'').toLowerCase());return;}
      if(!val){bad.push(t+' (no value)');return;}
      if(key==='vendor'){state.vendor=val.toLowerCase();return;}
      if(key==='baa'){if(/^(yes|1|true)$/i.test(val))baa.checked=true;else bad.push(t+' (only baa:yes)');return;}
      var v=norm(key,val);if(v===null){bad.push(t+' (no such value)');return;}
      sels[key].value=v;
    });
    state.text=words.join(' ');
    return bad;
  }
  function q1(v){v=v.toLowerCase().replace(/ /g,'-');return v;}
  function compose(){
    var parts=[];
    if(state.vendor)parts.push('vendor:'+state.vendor);
    if(cat.value)parts.push('cat:'+(cat.value.indexOf(' ')>-1?'"'+cat.value.toLowerCase()+'"':cat.value.toLowerCase()));
    if(tr.value)parts.push('trains:'+tr.value);
    if(z.value)parts.push('zdr:'+q1(z.value));
    if(rg.value)parts.push('region:'+rg.value);
    if(baa.checked)parts.push('baa:yes');
    if(state.text)parts.push(state.text);
    return parts.join(' ');
  }
  function apply(bad){
    var s=state.text,n=0,vd=state.vendor;
    rows.forEach(function(r){
      var d=r.dataset,ok=(!s||s.split(' ').every(function(w){return d.search.indexOf(w)>-1;}))&&
        (!vd||d.search.indexOf(vd)>-1)&&
        (!cat.value||d.cat===cat.value)&&(!tr.value||d.trains===tr.value)&&(!z.value||d.zdr===z.value)&&
        (!rg.value||d.region===rg.value)&&(!baa.checked||d.baa==='ok');
      r.hidden=!ok;if(ok)n++;
    });
    cnt.textContent=n+' of '+rows.length+' rows';
    none.hidden=n>0;
    var c=compose();
    parsed.textContent=(c?'filter: '+c:'no filter')+' → '+n+' row'+(n===1?'':'s')+(bad&&bad.length?' · ignored: '+bad.join(', '):'');
    parsed.classList.toggle('warn',!!(bad&&bad.length));
    var p=new URLSearchParams();
    if(s)p.set('q',s);if(vd)p.set('vendor',vd);
    ['cat','trains','zdr','region'].forEach(function(k){if(sels[k].value)p.set(k,sels[k].value);});
    if(baa.checked)p.set('baa','1');
    history.replaceState(null,'',(p.toString()?'?'+p:location.pathname)+location.hash);
  }
  q.addEventListener('input',function(){apply(parse());});
  q.addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();apply(parse());}});
  [cat,tr,z,rg,baa].forEach(function(el){el.addEventListener('change',function(){q.value=compose();apply([]);});});
  function reset(){q.value='';parse();apply([]);q.focus();}
  $('reset').addEventListener('click',reset);
  document.querySelectorAll('[data-reset]').forEach(function(b){b.addEventListener('click',reset);});

  // Initial state from URL params (old links: q, cat, trains, zdr, region, baa=1; new: vendor)
  var params=new URLSearchParams(location.search);
  state.text=(params.get('q')||'').trim().toLowerCase();
  state.vendor=(params.get('vendor')||'').trim().toLowerCase();
  Object.keys(sels).forEach(function(k){var v=params.get(k);if(v){var m=norm(k,v);if(m!==null)sels[k].value=m;}});
  if(params.get('baa')==='1')baa.checked=true;
  q.value=compose();

  // Sorting: tool name A–Z, or by status (favourable first), ties by name
  var ths=[].slice.call(table.tHead.rows[0].cells);
  ths.forEach(function(th,i){
    th.querySelector('button').addEventListener('click',function(){
      var cur=th.getAttribute('aria-sort'),dir=cur==='ascending'?'descending':'ascending';
      ths.forEach(function(h){h.setAttribute('aria-sort','none');});
      th.setAttribute('aria-sort',dir);
      var sign=dir==='ascending'?1:-1;
      rows.sort(function(a,b){
        if(i===0)return sign*a.dataset.name.localeCompare(b.dataset.name);
        var d=(+a.cells[i].dataset.rank)-(+b.cells[i].dataset.rank);
        return d?sign*d:a.dataset.name.localeCompare(b.dataset.name);
      });
      rows.forEach(function(r){tbody.appendChild(r);});
    });
  });

  // "/" focuses the query bar
  document.addEventListener('keydown',function(ev){
    if(ev.key==='/'&&!/input|select|textarea/i.test(document.activeElement.tagName)){ev.preventDefault();q.focus();}
  });
  apply([]);
})();
