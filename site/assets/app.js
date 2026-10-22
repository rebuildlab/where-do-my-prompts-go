(function(){
  var q=document.getElementById('q'),cat=document.getElementById('f-cat'),tr=document.getElementById('f-trains'),
      z=document.getElementById('f-zdr'),rg=document.getElementById('f-region'),cnt=document.getElementById('count');
  var rows=[].slice.call(document.querySelectorAll('#t tbody tr'));
  var params=new URLSearchParams(location.search);
  [['q',q],['cat',cat],['trains',tr],['zdr',z],['region',rg]].forEach(function(p){if(params.get(p[0]))p[1].value=params.get(p[0]);});
  function apply(){
    var s=q.value.trim().toLowerCase(),n=0;
    rows.forEach(function(r){
      var ok=(!s||r.dataset.search.indexOf(s)>-1)&&(!cat.value||r.dataset.cat===cat.value)&&
        (!tr.value||r.dataset.trains===tr.value)&&(!z.value||r.dataset.zdr===z.value)&&(!rg.value||r.dataset.region===rg.value);
      r.hidden=!ok;if(ok)n++;
    });
    cnt.textContent=n+' of '+rows.length+' tools';
    var p=new URLSearchParams();
    if(s)p.set('q',s);if(cat.value)p.set('cat',cat.value);if(tr.value)p.set('trains',tr.value);
    if(z.value)p.set('zdr',z.value);if(rg.value)p.set('region',rg.value);
    history.replaceState(null,'',p.toString()?'?'+p:location.pathname);
  }
  [q,cat,tr,z,rg].forEach(function(el){el.addEventListener('input',apply);});
  apply();
})();
